# Stage11 subtitle workstream — active work

WORKSTREAM: stage11
TASK_ID: S11-WX001
STATUS: IN_PROGRESS
CONTRACT_VERSION: 1.0.0
REQUIRES_WORKSTREAMS: stage11

## OBJECTIVE

Run an isolated FNS-247 WhisperX experiment to evaluate Japanese large-v3 recognition, Japanese forced alignment, and conditional pyannote diarization. This is a bounded technology evaluation, not a subtitle pipeline build or full-title ASR. Registration source SHA: aa6612200fb183bfcd2a18be557de8c818465a09.

## APPROVED_SCOPE

- Reuse the existing 27 user-judged audio samples and their existing labels, identity, hashes, timing, padding, Whisper, and ReazonSpeech evidence after read-only integrity checks.
- Select only 2–3 real continuous FNS-247 scenes with plausible speaker changes, retaining original absolute and inference-relative times.
- After the identity and resource gates pass, run WhisperX large-v3 Japanese ASR and forced alignment on the fixed 27-sample set; run pyannote only if its access and resource conditions pass.
- Compare new outputs read-only against existing Whisper and ReazonSpeech evidence using a protocol recorded before examining WhisperX outputs.
- Store private artifacts outside production paths with restrictive permissions; retain input/model/configuration provenance and raw outputs separately from evaluation.
- Update the canonical handoff with material results and return Stage11 to INACTIVE/NONE when the experiment ends.

## PROHIBITED_SCOPE

- Do not run full-title FNS-247 ASR, build or connect a production subtitle pipeline, or modify production code.
- Do not change existing sample labels, source evidence, original audio, Whisper/ReazonSpeech artifacts, or user judgments.
- Do not treat ASR output, model agreement, or generated speaker IDs as verified Japanese dialogue, ground-truth timing, or real-person identity; do not invent WER/CER without verified transcripts.
- Do not stop production services, kill processes to free GPU memory, alter existing CUDA/torch/Whisper environments, switch to CPU automatically, or retry after OOM.
- Do not bypass model access, licensing, or authentication requirements; do not expose tokens or credentials.
- Do not write to Stage11/Stage12 databases, queues, NAS subtitles, Jellyfin, or deployment targets; do not publish results or invoke Hermes.
- Do not commit audio, Japanese text, transcripts, tokens, or private experiment artifacts.

## ACCEPTANCE_CRITERIA

- Complete source identity and resource audits before inference; block inference if the original sample bytes cannot be verified or resources are insufficient.
- Preserve the predeclared evaluation and report executed sample count, dialogue/non-dialogue output, false-dialogue observations, alignment, diarization, runtime/resource use, and limitations; distinguish execution success from quality improvement.
- Do not claim product-quality PASS absent verified transcript/speaker truth; classify uncertain quality as INCONCLUSIVE.
- Leave production code and production state unchanged, with zero production writes and zero full-title ASR.
- Record results in the canonical handoff, set this workstream back to INACTIVE/NONE, and leave the full-title decision to the user.

## EVIDENCE

- User explicitly approved the isolated S11-WX001 FNS-247 WhisperX experiment and its fixed boundaries in this task request.
- Source branch at registration is teddy-subtitle-stage11, SHA aa6612200fb183bfcd2a18be557de8c818465a09; contract version remains 1.0.0.

## NEXT_DECISION

Verify the 27 sample identities and current GPU/runtime gates, then perform only the bounded experiment; after reporting, the user decides whether to authorize whole-title work.
