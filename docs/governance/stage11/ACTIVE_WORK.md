# Stage11 subtitle workstream — active work

WORKSTREAM: stage11
TASK_ID: S11-WX011
STATUS: BLOCKED
CONTRACT_VERSION: 1.0.0
REQUIRES_WORKSTREAMS: stage11

## OBJECTIVE

Use a small, independently labeled sample to compare completed S11-WX010 outputs with independent Japanese transcript, speech/non-speech, timing, and speaker references, and report measured accuracy and remaining uncertainty.

## APPROVED_SCOPE

- Read-only inspection of existing S11-WX010 evidence and model outputs.
- Select and freeze at most 16 short evaluation windows using the approved categories and existing verified core/time mappings.
- Verify the source and independence of transcript, speech/non-speech, speaker, and timing references.
- Compare only items with verified independent references; report unavailable dimensions as UNKNOWN.
- Record evaluation uncertainty, regressions, and resource evidence in a new private WX011 location.

## PROHIBITED_SCOPE

- No model inference, model replacement, Demucs rerun, or audio re-extraction.
- No changes to production models, services, caches, Qwen, Whisper Worker, or Stage11/Stage12 product code.
- No Hermes, Korean translation, subtitle generation, modification, or publication.
- No NAS, Jellyfin, or production database writes.
- No product threshold/default changes.
- No private Japanese transcripts, audio, personal review records, or detailed speaker results in Git.

## ACCEPTANCE_CRITERIA

- S11-WX011 registration and canonical remote readback pass.
- Existing WX010 source and output hashes and provenance links pass read-only verification and remain unchanged.
- A reproducible, non-duplicated sample of at most 16 windows is selected and frozen with source/core/time references.
- Each proposed independent reference has a verified source and independence assessment; unavailable references remain explicitly unavailable.
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

## NEXT_DECISION

Provide or authorize an independent Japanese transcript and time-aligned speech/speaker labels for the frozen 16 windows, with the reviewer blind to model outputs. Until then, accuracy evaluation remains incomplete and WX011 stays BLOCKED.
