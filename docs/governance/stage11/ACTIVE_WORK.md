# Stage11 subtitle workstream — active work

WORKSTREAM: stage11
TASK_ID: S11-WX008
STATUS: IN_PROGRESS
CONTRACT_VERSION: 1.0.0
REQUIRES_WORKSTREAMS: stage11

## OBJECTIVE

Run a bounded, isolated FNS-247 speaker-diarization evaluation and connect its speaker hypotheses to saved S11-WX007 WhisperX candidates. Measure whether diarization is useful without treating model output as speaker or transcript truth. Preserve the approved goal of reliable automatic Korean subtitles without per-title manual review in ordinary operation.

## APPROVED_SCOPE

- Reuse verified S11-WX001–WX007 evidence, especially the existing 27 inputs, WX007 A/B audio, Demucs stems, WhisperX results, user listening notes, JA timing index, and hashes. Do not repeat completed STT or Demucs runs.
- Select no more than four FNS-247 windows, each at most 120 seconds, with the sum of selected window durations no more than eight minutes. Prefer existing verified A/B inputs; extract only bounded new context from the FNS-247 source if a longer window is necessary. Keep each A/B pair on identical source bounds and record any window overlap.
- Evaluate only acoustic situations supported by prior independent evidence: multi-speaker turns, short exchanges, possible overlap, or speech/non-speech mixtures such as music or moans. Do not infer speaker count or sound type from STT/diarization output. Leave unsupported categories or windows unselected rather than forcing four samples.
- Before diarization output is inspected, freeze the selected-window list, rationale, source/video intervals, duration, source and input SHA-256 values, and the deterministic evaluation/linkage rules in the authorized private VM122 location. Keep audio, Japanese source text, judgments, and private evidence out of Git.
- Before model execution, check VM122's isolated environment, installed pyannote package, model terms/access, and RAM/VRAM. Use `pyannote/speaker-diarization-community-1` only. Verify access without accepting terms on the user's behalf or bypassing access controls. If access is unavailable, report `MODEL_ACCESS=BLOCKED` and do not substitute another model or cloud service.
- Run locally on VM122. Keep any required model download in an experiment-only cache; do not change the shared Hugging Face cache, operating virtual environments, model weights, Qwen, Whisper Worker, or production services. Do not upload audio to an external service.
- Compare original audio (A) with Demucs `htdemucs` vocals (B) over the same selected intervals. Reuse a WX007 stem only after its source-range, time-origin, duration, sample-count, and SHA match; otherwise run Demucs only on the selected bounded intervals. Keep Demucs dependencies isolated.
- Pin and record the pyannote package version, model revision, device, and inference settings before running. Use automatic speaker-count estimation; do not force two speakers. Preserve standard diarization and exclusive diarization as separate outputs when available. Exclusive output is not evidence that overlapping speech did not occur.
- Reuse saved WX007 WhisperX Japanese candidates and timestamps; do not run WhisperX or create new Japanese transcripts. For each candidate, record its interval intersections with diarization turns. Mark `SUCCESS` only when the candidate interval intersects turns for exactly one distinct speaker; mark `AMBIGUOUS` when multiple speaker IDs intersect; mark `FAILURE` when no speaker turn intersects. This is a speaker-link hypothesis only, not proof that the whole transcript or timing is correct.
- Report per window and input variant: detected speaker count, turn changes, possible merges/splits, short-utterance assignment risk, speech/non-speech assignment risk, standard/exclusive differences, overlap handling, STT-link success/ambiguous/failure counts, and processing time and CPU/GPU memory.
- Use speaker IDs only within a window. Do not equate `SPEAKER_00` across windows. Without independent speaker gold, report speaker accuracy and DER as `UNKNOWN`. Do not claim subtitle product-quality PASS from technical execution.
- Stop safely if resources are insufficient; do not stop or restart Qwen, Whisper Worker, or other services. No full-title diarization/ASR, other-title tests, production integration, subtitle edits, or publication.
- Update the canonical handoff with provenance, protocol/hash, outcomes, resource cost, and limits. After reporting, close the task through the existing governance procedure and return the router and Stage11 active-work file to `INACTIVE / TASK_ID NONE` unless an unresolved blocker requires the task to remain explicitly blocked.

## PROHIBITED_SCOPE

- No full-title FNS-247 diarization or ASR; no other-title experiment; no unapproved model or cloud API.
- No operational Demucs/WhisperX/diarization pipeline implementation or integration; no Stage11/Stage12 product code, subtitle generation, translation, correction, deletion, deployment, or publication.
- No changes to subtitle identity, order, timing ownership, translation policy, Hermes's semantic role, deterministic code's timing/publication role, or Stage12 ownership/no-overwrite boundaries.
- No forcing a speaker count, cross-window speaker identity, transcript truth, or absence of overlap from diarization output alone.
- No modification of NAS/Jellyfin/operating databases, services, timers, original media, existing WX evidence, Qwen/Whisper Worker, shared model caches, or operating environments. No NAS/Jellyfin/publication writes.
- No title-, cue-, phrase-, or sample-specific production behavior; no private audio, Japanese text, credentials, judgments, or private evidence in Git.

## ACCEPTANCE_CRITERIA

- Router and this file register the same `S11-WX008`, `IN_PROGRESS`, `stage11`, and contract `1.0.0`; the existing governance structural and task-authorization checks pass, and the activation commit is confirmed on the canonical remote before audio extraction or model execution.
- Model terms/access and isolated environment are verified without exposing credentials or accepting terms for the user. Report `MODEL_ACCESS=PASS` or `BLOCKED`; a blocked result causes no fallback model run.
- The frozen selection contains at most four windows, each at most 120 seconds, with summed duration at most eight minutes. Record selection rationale, interval, duration, and hashes before inspecting diarization output; report fewer eligible windows when evidence is insufficient.
- For each selected window, compare original and Demucs audio with the same authorized pyannote version/model/settings, or record each failed/unrun condition and reason. Verify input identity and Demucs time correspondence.
- Report original/Demucs speaker counts and turns, STT candidate `SUCCESS`/`AMBIGUOUS`/`FAILURE` linkage counts, merge/split and short-turn risks, overlap/exclusive handling, non-speech assignment risk, per-condition cost, and `FULL_TITLE_READINESS` as `근거 있음`, `추가 검증 필요`, or `판단 불가`. Speaker accuracy and DER remain `UNKNOWN` without independent speaker gold.
- Distinguish technical execution status from diarization quality and from Korean subtitle product quality. Do not claim full-title readiness without supporting evidence; preserve the no-per-title-manual-review goal.
- Production changes, whole-title runs, other-title tests, deployment/publication, and NAS/Jellyfin writes remain zero. Canonical handoff is updated, and task closure/routing state is validated and confirmed on the remote.

## EVIDENCE

- The user explicitly approved S11-WX008 for a bounded FNS-247 speaker-diarization experiment, the `pyannote/speaker-diarization-community-1` target, original-versus-Demucs comparison, the listed safeguards, and these completion conditions.
- Canonical base: `teddy-subtitle-stage11` at `4cccb29c4673bd57cc8bef2d22553e65bba57787`; common and Stage11 contracts are approved at version `1.0.0`.
- S11-WX007 completed with A=27, B=6, C=0 and all four WhisperX/Demucs conditions; its private VM122 evidence and hashes are documented in the canonical handoff and stored under `/home/teddy/stage11-whisperx-ab-private/analysis/S11-WX007`.
- S11-WX007 product quality is `INCONCLUSIVE`; Japanese transcript and absolute boundary accuracy are `UNKNOWN`. Its candidates remain hypotheses.

## NEXT_DECISION

After the S11-WX008 report, the user decides whether to authorize any broader FNS-247 isolated validation. This task does not authorize whole-title processing or production integration.
