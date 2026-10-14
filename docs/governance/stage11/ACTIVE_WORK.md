# Stage11 subtitle workstream — active work

WORKSTREAM: stage11
TASK_ID: S11-WX004
STATUS: IN_PROGRESS
CONTRACT_VERSION: 1.0.0
REQUIRES_WORKSTREAMS: stage11

## OBJECTIVE

Offline evidence analysis of the saved S11-WX003 results for the fixed 27 FNS-247 samples, with a private A/B listening-review packet. No model execution or human-listening claim is included.

## APPROVED_SCOPE

- Reuse only the saved 27-sample WhisperX run, the existing Whisper/ReazonSpeech results at paths identified by canonical handoff and evidence manifests, the existing user judgments, and the approved 2026-10-11 evidence evaluation. Do not infer or guess a missing source path.
- Read from VM122 `/home/teddy/stage11-whisperx-ab-private` and the original prior-result paths after registration is remotely confirmed. Verify sample IDs, SHA-256, source ranges, context padding, saved model revisions, and output presence read-only before comparison.
- Compare the four dialogue-labelled WhisperX-empty samples (`clip-003`, `clip-005`, `clip-006`, `clip-008`) with existing Whisper/ReazonSpeech hypotheses, input duration/VAD metadata, and absolute timing. Report causes as hypotheses or `UNKNOWN` unless the saved evidence proves them.
- Compare the four non-dialogue-labelled WhisperX-output samples (`clip-014`, `clip-015`, `clip-017`, `clip-020`) with saved evidence and mark each `FALSE_DIALOGUE_CANDIDATE`; do not declare a confirmed hallucination without human audio verification.
- Review all nine existing forced-alignment outputs and compare raw/aligned WhisperX timing, saved Whisper timing, core/body range, context range, and title-absolute time. Keep start/end boundary truth `UNKNOWN` without human reference timing.
- Prepare a concise 27-sample summary and a private human listening packet with the user-requested text, ranges, original audio references, and one listening question per target. Prefer references to existing private WAVs; copy only when necessary and only within private storage.
- Mark `HUMAN_LISTENING=NOT_DONE` unless the user separately reports actual human playback and findings. Preserve transcript, boundary, and speaker truth as `UNKNOWN` where no reference exists.
- Store reports and any local-openable Markdown/HTML packet only in the VM122 private directory or another explicitly private temporary directory, with directories 0700 and files 0600. Do not add private artifacts to Git.
- Update the canonical handoff with aggregate evidence, limits, and the next decision. Restore this workstream and router to `INACTIVE/NONE` only after the packet and analysis are complete.

## PROHIBITED_SCOPE

- Do not invoke WhisperX, Whisper, ReazonSpeech, pyannote, Gemini, Hermes, Demucs, or any other ASR/acoustic model. Do not install/download models or packages.
- Do not make an AI claim that it listened to or verified audio. Do not infer Japanese transcript truth, boundary truth, or speaker truth from model agreement or output presence.
- Do not modify original WAVs, saved JSON/results, model artifacts, user judgments, or their manifests.
- Do not process the full FNS-247 title or any samples beyond the existing 27.
- Do not change Stage11/Stage12 product code, production services/GPU configuration, databases, queues, timers, NAS, Jellyfin, subtitles, or published artifacts.
- Do not translate, generate, replace, publish, or approve subtitles. Do not create new model calls or experiments.
- Do not commit audio, Japanese source/transcript text, private review packets, private paths, credentials, or other experiment artifacts.

## ACCEPTANCE_CRITERIA

- Register this task in both routing and Stage11 active-work metadata; both required governance checks pass and the activation commit is confirmed on the current canonical remote before any VM/result access or new analysis.
- Validate provenance and integrity for all 27 sample IDs and their stored outputs without altering inputs or prior results.
- Produce explicit A/B findings for all four missing candidates, all four non-dialogue conflicts, all nine alignment cases, and a minimal summary of all 27 samples. Separate measured differences from hypotheses and unknowns.
- The private review packet connects each included clip to the original audio path, absolute time, user label, saved Whisper/WhisperX/Reazon hypotheses when present, raw/aligned timing, and one question for a human listener.
- The packet and final report say `HUMAN_LISTENING=NOT_DONE` unless actual human listening is reported; accuracy/truth fields remain `UNKNOWN` as applicable.
- Make no model calls, production writes, full-title ASR, or source-result changes. Preserve the private permissions and update the canonical handoff.
- When no analysis or packet work remains, restore `INACTIVE/NONE`, run the structural governance check, and verify the final canonical remote HEAD.

## EVIDENCE

- User explicitly approved S11-WX004 for offline comparison and listening-review preparation, with zero new model execution.
- Canonical branch `teddy-subtitle-stage11` was fetched at `1beda4cd71d44b775a457fe2c8d3326e2e716e1d`; Stage11 contract is APPROVED v1.0.0 and initially `INACTIVE/NONE`.
- S11-WX003 saved 27/27 WhisperX outputs, 9/13 dialogue candidates, 4/14 non-dialogue conflicts, and 9/9 alignment outputs. Japanese transcript, exact boundary, and speaker truth remain unresolved.
- The specified discovery evaluation is prior evidence; it records user audio-presence judgments, not verified Japanese transcripts or manual boundary truth.

## NEXT_DECISION

After the private packet is ready, the user or a human Japanese listener reviews prioritized original audio and records transcript/timing findings. Then decide separately what evidence is still needed before approving any whole-title experiment.
