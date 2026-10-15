# Stage11 subtitle workstream — active work

WORKSTREAM: stage11
TASK_ID: S11-WX009
STATUS: IN_PROGRESS
CONTRACT_VERSION: 1.0.0
REQUIRES_WORKSTREAMS: stage11

## OBJECTIVE

Use the completed S11-WX008 FNS-247 diarization evidence to obtain an independent user listening judgment for the two windows where original and Demucs speaker counts differed, then prepare a proposal for a separate, user-approved whole-title isolated evaluation. This task does not run that evaluation.

## APPROVED_SCOPE

- Reuse exactly the WX008 windows `B-early-JA` (video 00:01:34.575–00:02:04.575) and `B-middle-JA` (video 01:03:33.601–01:04:03.601), including existing original/Demucs audio, regular/exclusive diarization outputs, and linked WX007 WhisperX evidence; verify file hashes and provenance without rerunning models or extracting audio.
- Prepare a private, offline review package with the four existing audio files. Do not expose model speaker counts, turns, IDs, transcripts, or hypotheses before the user's first-pass judgment. Record the user's independent judgments only after the user returns them.
- After the user judgment is available, compare it with existing diarization and STT evidence, preserving uncertainty and reporting accuracy as `UNKNOWN` where speaker truth is insufficient.
- Prepare a proposal only for a possible future FNS-247 whole-title isolated experiment using existing WX007–WX009 evidence. A separate user approval is required before that experiment.
- Keep audio, Japanese text, and user judgment data in the approved VM122 private storage. Git may contain only non-sensitive protocol, status, provenance identifiers, hashes, and summarized findings.

## PROHIBITED_SCOPE

- No new audio extraction; no Demucs, WhisperX, or pyannote inference; no whole-title or other-title processing.
- No model, production pipeline, Stage11/Stage12 code, Qwen, Whisper Worker, operating service, or model environment changes.
- No Hermes, translation, subtitle generation/editing, timestamps, IDs, ordering, deployment, publication, or NAS/Jellyfin/production DB writes.
- Do not present model output, external JA cue presence, or user uncertainty as ground truth. Do not commit private audio, Japanese text, token, or listening judgments.
- Preserve the approved Stage11 contract and Stage12 ownership and publication boundaries.

## ACCEPTANCE_CRITERIA

- The router and this file use the same `S11-WX009` task ID and status, and task registration passes the existing governance checks on the canonical branch before private review materials are prepared.
- The two target windows' existing source files, outputs, WX007 links, and SHA-256 values are verified; no source audio or model output is regenerated.
- The offline package contains exactly the four approved existing audio variants, permits simple A/B playback, contains no model predictions or Japanese transcript, and makes no external network requests.
- The user can record distinct-voice count (including `UNKNOWN`), approximate change times, speech/non-speech vocalization kinds, uncertainty, and optional notes; transcript and phoneme boundaries are optional.
- At the first checkpoint the task is `READY_FOR_USER_REVIEW`, package path and hash are reported, and `USER_LISTENING=PENDING`. Do not infer or fill user judgments.
- After the user judgment, compare evidence, prepare the whole-title proposal for separate approval, record limitations, and close the task through the existing governance procedure.
- `MODEL_RUNS=0`, `PRODUCTION_CHANGES=0`, and `NAS_JELLYFIN_WRITES=0` throughout this task.

## EVIDENCE

- S11-WX008 completed and closed on the canonical `teddy-subtitle-stage11` branch at base HEAD `5363b0c96fc98d03003c1ff951f8fbb9b1922f74`; its private source/result hashes and limitations are recorded in the canonical handoff and WX008 manifests.
- At registration, no WX009 private review package or user judgment has been created. These will be recorded only after registration is confirmed on the canonical remote.

## NEXT_DECISION

The user returns independent listening judgments, then decides separately whether to approve any proposed whole-title FNS-247 isolated evaluation. This task does not authorize that evaluation or production integration.
