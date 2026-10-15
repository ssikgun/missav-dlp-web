# Stage11 subtitle workstream — active work

WORKSTREAM: stage11
TASK_ID: S11-WX007
STATUS: IN_PROGRESS
CONTRACT_VERSION: 1.0.0
REQUIRES_WORKSTREAMS: stage11

## OBJECTIVE

Run a private, controlled FNS-247-only comparison of Demucs separation and WhisperX VAD onset changes across the existing 27 diagnostic inputs and eligible new general and special-acoustic inputs. Assess whether improvements generalize beyond the existing cases while preserving the approved goal of reliable Korean subtitles without per-title manual review in ordinary operation.

## APPROVED_SCOPE

- Reuse the prior S11-WX006 source, external-JA timing, and VM122 27-sample evidence. Reconnect its source identifiers, SHA-256 values, mappings, and exact Core/Context ranges before use; do not recreate completed extraction or inference.
- A group is the existing 27 inputs: 13 dialogue-labeled and 14 non-dialogue-labeled. Preserve their Core/Context ranges and audio identities. Reuse a saved BASE result only if input hash, WhisperX/model, VAD, decoding, and code conditions exactly match; otherwise run the condition.
- B group targets six new FNS-247 inputs: one valid affine-mapped JA-cue window and one JA-gap window in each of the early, middle, and late thirds. Freeze core/window duration, padding, minimum spacing, eligibility, deterministic selection algorithm, and seed before viewing any new STT output. Exclude all A full-model-input Context and all B input-Context overlaps. If an eligible stratum cannot be filled, report B_PARTIAL without arbitrary substitution. A JA gap is not a no-speech gold label.
- C group targets up to six new windows, at most two each for music with speech, whisper/weak speech, and moaning or non-dialogue sound. Confirm labels from independent original-audio evidence without using STT text; do not force unconfirmed types. Exclude all A/B full-model-input Context overlaps.
- Save the frozen A/B/C selection manifest, source references, Core/Context intervals, hashes, selection protocol, and independent C evidence in the approved private VM122 location before model execution. Keep audio, Japanese source text, judgments, and private evidence out of Git.
- For each selected input, compare BASE (original audio, onset 0.50/offset 0.363), VAD (original audio, onset 0.45/offset 0.363), DEMUCS (Demucs speech stem, onset 0.50/offset 0.363), and COMBINED (Demucs speech stem, onset 0.45/offset 0.363). Keep WhisperX 3.8.6, large-v3, Japanese, decoding, 30-second VAD chunk, and all other settings fixed. Declare and record the exact Demucs model/version/stem/settings before running it.
- Run only in the isolated VM122 experiment environment. Check available RAM/VRAM, preserve Qwen, Whisper Worker, production services, model weights and virtual environments, run conditions sequentially, and stop safely if resources are insufficient. Keep Demucs dependencies separate. Do not run full-title ASR or Demucs, modify NAS source/prior evidence, or connect Demucs to the operating Stage11 pipeline.
- Verify Demucs output duration, sample count, time origin, and correspondence to its original input. Exclude uncertain mappings from boundary-accuracy claims. Individually report candidate-generation changes for `clip-003`, `clip-005`, `clip-006`, and `clip-008`; generated text alone is not a confirmed recovery.
- Report by A/B/C and condition: dialogue-candidate detection and omissions; Japanese transcription accuracy only against independent gold (otherwise UNKNOWN); non-dialogue false-text risk; boundary changes and accuracy only with boundary gold; and Demucs/WhisperX time, VRAM, and memory cost. Record improvement, regression, no change, or indeterminate. A-only improvement cannot establish general quality PASS.
- Update the canonical handoff with provenance, protocol, results, limits, and product-quality status. After the report, return router and Stage11 ACTIVE_WORK to INACTIVE / TASK_ID NONE using the existing governance procedure.

## PROHIBITED_SCOPE

- No operational subtitle generation, Stage11/Stage12 product-code changes, integration of Demucs into production, deployment, publication, replacement, or title-specific production behavior.
- No other-title experiments, whole-title FNS-247 ASR/Demucs, or use of model results to revise the frozen B/C selection.
- Do not modify or remove the NAS original, prior sample inputs/results, VM122 Qwen or Whisper Worker, production services, model weights, or operating virtual environments. Do not stop or restart existing services.
- No NAS/Jellyfin/publication writes, external audio/text transfer, or Git inclusion of audio, Japanese source text, credentials, judgments, or private evidence.
- Do not present output presence as transcription accuracy, JA gaps as no-speech truth, or technical execution as Korean subtitle product-quality PASS. Do not make per-title manual review a product requirement.

## ACCEPTANCE_CRITERIA

- Stage11 registration matches the router, uses contract 1.0.0, and passes the existing task-authorization and structural governance checks; the activation commit is confirmed on the canonical remote before new audio extraction, Demucs, or WhisperX inference.
- Source media, the 313 valid mapped JA cues and affine timing evidence, and all existing 27 sample identities/ranges/hashes are linked to verified prior evidence. Any missing or mismatched identity is reported as an integrity failure without substitution.
- The A inputs are compared under all four conditions or each unavailable/failed condition is explicitly recorded. B is six selected and compared when every stratum has eligible non-overlapping candidates, otherwise its exact partial state and reason are reported. C includes only independently supported types and reports its actual count and any unconfirmed types.
- Selection protocol and A/B/C manifest are saved and hash-frozen before model execution. No new STT output informs selection.
- The four prior VAD-miss clips are individually compared. Group/condition reports include all approved evaluation categories, resource costs, and improvement/regression/no-change/indeterminate outcomes. Transcription or boundary accuracy remains UNKNOWN without independent gold.
- Product quality is INCONCLUSIVE unless the evidence supports the approved general quality goal; A-only gains do not pass it. Report limitations and retain the no-per-title-manual-review goal.
- No production changes, deployment, subtitle generation/publication, other-title tests, NAS/Jellyfin writes, or Git inclusion of private data occur. Handoff and final INACTIVE/NONE routing are validated and confirmed on the canonical remote.

## EVIDENCE

- User explicitly approved S11-WX007 for the FNS-247 isolated Demucs/WhisperX VAD experiment and the scope, settings, safeguards, and completion reporting recorded above.
- Canonical base: `teddy-subtitle-stage11` at `3f8ad44c78012de33567787ad354b07b3d924684`; common and Stage11 contracts are APPROVED v1.0.0.
- The preceding read-only preflight linked FNS-247 to `/volume1/video/video2/JAV/FNS/FNS-247/FNS-247.mp4`, duration 02:54:20.40, AAC 48 kHz stereo; saved Normal E2E JA evidence contains 313 valid cues and a 40-anchor affine map; VM122 `/home/teddy/stage11-whisperx-ab-private` has verified hashes for all 27 existing inputs.
- S11-WX006 recorded VAD exclusion for `clip-003`, `clip-005`, `clip-006`, and `clip-008`. Transcript, boundary, speaker, and general product truth remain unverified until this task collects adequate independent evidence.

## NEXT_DECISION

Complete the bounded experiment and report whether the combined evidence supports any further user-approved Stage11 work; this registration does not authorize operational integration or publication.
