# Stage11 subtitle workstream — active work

WORKSTREAM: stage11
TASK_ID: S11-WX011
STATUS: IN_PROGRESS
CONTRACT_VERSION: 1.0.0
REQUIRES_WORKSTREAMS: stage11

## OBJECTIVE

Prepare a blinded listening package from the already frozen S11-WX011 sample so the user can independently note speech presence, approximate speaker count and timing, and Korean phonetic impressions. Use those notes only as listening evidence; they are not Japanese transcript truth. Continue to report which accuracy dimensions remain unknown.

## APPROVED_SCOPE

- Read-only inspection of existing S11-WX010 evidence and model outputs.
- Select and freeze at most 16 short evaluation windows using the approved categories and existing verified core/time mappings.
- Verify the source and independence of transcript, speech/non-speech, speaker, and timing references.
- Compare only items with verified independent references; report unavailable dimensions as UNKNOWN.
- Record evaluation uncertainty, regressions, and resource evidence in a new private WX011 location.
- Prepare blinded WAV copies from verified WX010 original-audio WAVs for the existing frozen 16 windows, with a separate private mapping and blank listening form; initially ask the user to listen only to S01–S03.
- Preserve the user's first-pass entries unchanged before comparing them with any model or subtitle evidence. Treat Korean phonetic notes as auxiliary listening notes, never as Japanese transcript references.

## PROHIBITED_SCOPE

- No model inference, model replacement, Demucs rerun, or audio re-extraction.
- No changes to production models, services, caches, Qwen, Whisper Worker, or Stage11/Stage12 product code.
- No Hermes, Korean translation, subtitle generation, modification, or publication.
- No NAS, Jellyfin, or production database writes.
- No product threshold/default changes.
- No private Japanese transcripts, audio, personal review records, or detailed speaker results in Git.
- Do not expose model output, external Japanese subtitles, predicted speaker counts, or answer hints in the user-facing blind package.

## ACCEPTANCE_CRITERIA

- S11-WX011 registration and canonical remote readback pass.
- Existing WX010 source and output hashes and provenance links pass read-only verification and remain unchanged.
- A reproducible, non-duplicated sample of at most 16 windows is selected and frozen with source/core/time references.
- Each proposed independent reference has a verified source and independence assessment; unavailable references remain explicitly unavailable.
- The blind package contains exactly the 16 frozen windows, uses only verified original WX010 WAV inputs, and passes source-frame/output-SHA checks; mapping remains private and the user-facing directory contains only blind audio and a blank form.
- The user is asked to listen to S01–S03 first; Korean phonetic notes are explicitly excluded from Japanese transcript scoring.
- Evaluations, denominators, unknown items, regressions, and uncertainty are reported from evidence only.
- No model execution, extraction/Demucs rerun, production change, or subtitle publication occurs.

## EVIDENCE

- User approved S11-WX011 on 2026-10-16 after S11-WX010's independently verified 1,050/1,050 outputs.
- Existing locks: parent R6 protocol `fe580bea7b7c8cc27828e5af8e24dc8c766bb064e075607cfafb0614cc8f0e22`; successor-004 environment `838740b33f35403c6c76698eab87dc25e5959a8b6e713814d4720977ecbe6591`.
- Frozen WX010 core plan `6343c841d07b9f04e79967b3d406f2d3d35efef260967a08fddbe6e449d68752`; JA index `b63745df3a9bfa3f7ec895b289c12d6b069f7e8d2024355e13e24c63ef21d270`.
- Canonical registration was read back at `dd9a738d684bba1e3d71388b4782932dd1c92631`. WX010 artifacts were not changed; its preceding independent audit verified 1,050/1,050 outputs, with 0 missing or invalid.
- Frozen WX011 selection protocol SHA-256 `73f77e4852f187faf1ee87e68a9fb99b6bfb39ee59b09830098fc0048c694325`; private sample manifest SHA-256 `3b4ac21598d3a8f7e01588a760a0b6f88644d3100519705f789641616abbf478`; safe aggregate SHA-256 `bf57c2ecd1ba44bac36603136bac9cd2917a8d210d16e23fb41c978cf9c2457e`. The frozen set contains 16 non-overlapping windows (A/B/C/D/E: 3/3/3/3/4), totaling 188.613 seconds after owner-core clipping. Referenced source and result hashes were independently rechecked; the private artifacts contain no transcript text.
- Independent references are partial: transcript truth `0/16`; speech-presence labels `10/16` (7 speech-present, 3 non-dialogue); window-level speaker-count references `2/16`; exact boundary references `0/16`. WX005 confidence was not provided and its export does not attest model-hypothesis exposure; WX009 is a high-confidence first-pass review whose package excluded model hypotheses and transcripts.
- In these selected windows, existing candidate-occurrence counts were 20/20/23/23 for original/VAD 0.50, original/VAD 0.45, Demucs/VAD 0.50, Demucs/VAD 0.45. Candidate presence occurred in 4/7 speech-labeled windows for each original condition and 5/7 for each Demucs condition; it occurred in 2/3 non-dialogue-labeled windows for each original condition and 3/3 for each Demucs condition. These are interval-overlap risk indicators, not verified transcripts or confirmed hallucinations. VAD thresholds had identical candidate counts in all 16 sample windows.
- WX007 regression presence: clip-003 had no candidate in any condition; clip-005/006 had candidates in all four; clip-008 had candidates only in the two Demucs conditions. Candidate occurrence does not prove accurate recovery. In the two WX009 speaker-count windows, the user's count was 2; prior WX008 Demucs output also counted 2 while original output counted 3 and 1 respectively. This small comparison does not establish DER or general speaker accuracy.
- Japanese transcription accuracy, exact boundary accuracy, and speaker accuracy/DER remain `UNKNOWN`; product quality is `INCONCLUSIVE`. `R5_MANIFEST_PROVENANCE=UNRESOLVED`. Model executions, audio extraction reruns, Demucs reruns, Hermes executions, production changes, NAS/Jellyfin writes, and subtitle publication are all 0.
- User approved a blinded listening evidence package on 2026-10-16 because no Japanese-speaking reviewer is available. The user may record speech presence, approximate speaker count/timing, confidence, and Korean phonetic impressions. Those impressions are not Japanese transcript truth and cannot support CER/WER, exact transcription accuracy, DER, or a product-quality PASS.
- Frozen sample manifest SHA-256: `3b4ac21598d3a8f7e01588a760a0b6f88644d3100519705f789641616abbf478` (16 windows; no additions or reselection). Canonical `IN_PROGRESS / S11-WX011` was read back at `fbb183f026d3773c49d9e2b4773e1eae5d7406b2` before package generation.
- Blind package verification PASS: 16 exact-frame WAVs (188.613 seconds total) were copied from 14 verified original WX010 core WAVs. Each output's PCM bytes match its selected source frame range; source hashes, frame counts, format, and time mapping passed. Private provenance SHA-256 `c28a02c0f8615d61cb73bd525e3d5469fd87725e0148a624389a1ca511aa97f7`; safe package summary SHA-256 `4c556b42d6c47e54aed94b847023f557247c0202a80c052ac6e4549955a3113d`. User-facing folder contains only S01–S16 WAVs, an empty 16-row CSV, and listening instructions. Source sample manifest and WX010 evidence remain unchanged.
- Private package path: `/home/teddy/stage11-whisperx-ab-private/analysis/S11-WX011/blind-listening-package-v1/`. Mapping and detailed hashes are in its private sibling directory, outside `user-facing/`; none are in Git. User listening is pending. No model execution, video audio extraction, Demucs rerun, Hermes, production change, NAS/Jellyfin write, or subtitle publication occurred.

- 2026-10-17 S01–S03 comparison was archived in a new VM122 private evidence set. User listening and the Gemini-reported hypotheses are stored as separate sources; the current listening occurred after Gemini exposure and is not strict blind evidence. The frozen sample manifest SHA remains 3b4ac21598d3a8f7e01588a760a0b6f88644d3100519705f789641616abbf478; WX010 input/output references and time mappings passed read-only revalidation. Safe private artifact index SHA-256: 62b5c76c1fa1efa8c4042f457a3935e21242ec9ccb829c2c20711797d6dc9444.
- All three user-reported samples contain speech. Only S02 has a direct current speaker-count judgment (3, after Gemini exposure); S01 and S03 are qualitative agreement with Gemini’s two-voice hypothesis. S01 exactly matches the previously recorded WX009 window, whose separate first-pass judgment counted 2 voices; the records remain separate.
- In the fixed windows, overlapping WhisperX candidate segments intersected S01 as 2 per condition, S02 as 2 per condition, and S03 as 1/1/2/2 (original .50/.45, Demucs .50/.45). These are overlapping core outputs, not dialogue-turn counts; no exact repeated text was found within a condition, but overlapping/contradictory output risk remains. Gemini’s approximate start points intersected candidate intervals at S01 3/5 original and 4/5 Demucs, S02 6/6 in all conditions, and S03 3/6 in all conditions. This is descriptive time overlap only.
- pyannote exclusive output for S02 found 3 core-local IDs in both inputs (10 original turns, 9 Demucs turns); the count agrees with the user’s window-level count, but no ID-to-person mapping is verified. S01 spans core-001 and core-002, so IDs were not combined; core-001 counts were 3 original / 2 Demucs, and core-002 counted 2 in both. S03 counted 2 in both, with 25 original versus 11 Demucs exclusive turns, indicating different turn fragmentation. These are model outputs, not DER or identity accuracy.
- Japanese transcript accuracy, exact boundary accuracy, speaker DER, and false-dialogue accuracy remain UNKNOWN; product quality remains INCONCLUSIVE. No Japanese transcript or Gemini Korean translation text was supplied for a semantic text comparison. No models, extraction, Demucs, Hermes, production, NAS/Jellyfin, or publication were run for this comparison.

- 2026-10-17 S04–S16 user listening notes were preserved unchanged in the VM122 private comparison archive at `/home/teddy/stage11-whisperx-ab-private/analysis/S11-WX011/comparisons/S04-S16-user-listening-wx010-20261016T152030Z/`. Review time, confidence, and whether this pass was blind were not provided; do not claim strict blinding. Korean phonetic notes are not Japanese transcript truth.
- The frozen sample manifest SHA-256 remains `3b4ac21598d3a8f7e01588a760a0b6f88644d3100519705f789641616abbf478`. The original and Demucs inputs, all 16 listening WAVs, six WX010 condition manifests, and 112 referenced output files passed read-only SHA, source/core/lock, and time-mapping checks. The maximum audio/video timestamp mapping delta was 0 ms. Existing R5 extraction-manifest provenance remains `UNRESOLVED`.
- In S04–S16, user notes mentioned speech in 10 windows and nonverbal vocalizations without reported speech in 3. WhisperX candidate-occurrence counts were 15/15/17/17 for Original .50 / Original .45 / Demucs .50 / Demucs .45. Candidate presence was 9/13 for either Original condition and 11/13 for either Demucs condition; among speech-noted windows it was 7/10 versus 8/10, and among vocalization-only notes it was 2/3 versus 3/3. These are candidate-presence indicators, not recovery, accuracy, or confirmed false dialogue.
- VAD .45 changed no candidate counts in these windows; clipped candidate intervals differed in 1 Original window and 3 Demucs windows. Demucs-only candidates occurred in two windows, including one user-reported speech window and one vocalization-only window; two speech-noted windows had no candidate in any condition. Five windows had time-overlapping candidate spans from neighboring core contexts. Exact duplicate wording was not evaluated in the surfaced comparison; overlapping spans and broad candidates remain review risks.
- Exclusive pyannote speaker counts differed between Original and Demucs in 4/13 windows; regular/exclusive output also diverged within some windows. Turn counts varied by input. These are model-output differences only: user notes lack exact speaker/time references, so speaker accuracy and DER remain UNKNOWN.
- The separate S03 check found candidate intervals ending by about 4.60 seconds, while the previously reported Gemini onset guesses include about 5 and 7 seconds. The user did not confirm those exact times. They remain an unverified discrepancy, not a confirmed omission.
- No model inference, audio re-extraction, Demucs rerun, Hermes, production change, NAS/Jellyfin write, or subtitle publication occurred. WX010 and the frozen WX011 manifest remain unchanged. Japanese transcription accuracy, exact boundary accuracy, and speaker DER remain UNKNOWN; product quality remains INCONCLUSIVE.

- 2026-10-17 S03 listening follow-up was appended as a new VM122 private record at `/home/teddy/stage11-whisperx-ab-private/analysis/S11-WX011/comparisons/S03-late-speech-user-followup-20261017T013754Z/USER_LISTENING_SUPPLEMENT.json` (SHA-256 `4287a4c4cabbbaa09fd12caef35c0c70dac0c59ce66c8fb47ffcaa1b9742f60f`; index SHA-256 `5015ef880f70e3bb66565e8ea197bdc1dd8765bdc218da3ac3e959ad241178d8`). The 16-window manifest still hashes to `3b4ac21598d3a8f7e01588a760a0b6f88644d3100519705f789641616abbf478`; the prior S01–S03 listening record and index were hash-checked and left unchanged.
- 2026-10-17 S04/S08/S13 existing WhisperX text outputs were audited read-only. The frozen sample manifest (`3b4ac21598d3a8f7e01588a760a0b6f88644d3100519705f789641616abbf478`) and blind mapping (`c28a02c0f8615d61cb73bd525e3d5469fd87725e0148a624389a1ca511aa97f7`) matched. Target clip WAVs, all referenced condition/core output JSONs and their source input WAVs matched stored SHA values; candidate intersections, parent lock, ownership references and source/video time mapping were rechecked.
- Candidate counts in Original .50 / Original .45 / Demucs .50 / Demucs .45 order were S04 1/1/1/1, S08 1/1/1/1, and S13 0/0/1/1. Exact strings varied across conditions: S04 and S08 each had three distinct variants; S13's two Demucs variants differed. The Japanese strings remain only in existing private WX010 output files; no text copy was added to Git. The segments are broad context-level candidates, not utterance-length evidence; S04's candidate came from an adjacent processing core. Candidate shape alone does not establish vocalization, dialogue, hallucination, or accuracy.
- The original Japanese is available through a verified read-only VM122 command using manifest references and SHA checks. Until the user views it alongside the clip, text-form classification remains `AMBIGUOUS`; Japanese transcription accuracy and misrecognition remain `UNKNOWN`. No model, audio, or existing result was changed or rerun.
- The user now directly reports that conversation continues in S03's latter part (`USER_REPORTED_YES`). This listening followed Gemini exposure, so it is not strict blind evidence. Exact start/end times and Japanese transcript accuracy remain `UNKNOWN`; Gemini's approximate 5 s and 7 s times remain model estimates. The late-dialogue omission is `STRONGLY_SUSPECTED, NOT_CONFIRMED`.
- S11 and S15 remain priority missed-dialogue investigation cases: user-reported speech with zero candidates in each of the four saved WhisperX conditions. Candidate absence does not by itself confirm a miss without independently located speech timing/content. No fixed samples, source audio, or model outputs were changed; model executions, extraction/Demucs reruns, Hermes, production changes, NAS/Jellyfin writes, and subtitle publication remain 0. Japanese accuracy and final product quality remain `UNKNOWN` and `INCONCLUSIVE`, respectively.

## NEXT_DECISION

Keep Japanese transcription accuracy, exact boundary accuracy, and speaker DER as UNKNOWN. The immediate next decision is the user's private review of the exact S04/S08/S13 Japanese strings alongside the existing clips; only then classify their form as short-vocalization candidate, substantive-dialogue candidate, or ambiguous. Do not infer accuracy or hallucination from candidate existence or segment length. Keep S03/S11/S15 as omission-risk cases, product quality INCONCLUSIVE, and ordinary operation free of per-title manual review.
