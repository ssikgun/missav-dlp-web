Warning: truncated output (original token count: 200220)
Total output lines: 12931

# Teddy Downloader / missav-dlp-web — CURRENT HANDOFF

## 2026-10-15 — S11-WX010 registered for isolated FNS-247 whole-title evaluation

The user approved S11-WX010 after reviewing the WX009 proposal. The task is registered only in Stage11 under contract v1.0.0: FNS-247 full-title Demucs vocals, four frozen WhisperX original/Demucs × VAD conditions, two original/Demucs pyannote conditions, mapped JA coverage comparison, and evidence-quality analysis. Hermes, translation, subtitle generation/publication, production code or service changes, other-title processing, and NAS/Jellyfin/database writes are excluded. The user's final product goal remains automatically generated Korean subtitles without per-title manual review; WX010 is audio evidence collection only.

Registration base: `2d67ac1fe3a5379d627fcba1a0dd91325858296c`; registration commit `a5ea85acc05f8bcf4ef42d75728b92cd9cb49f71` is confirmed on `origin/teddy-subtitle-stage11`. The router and Stage11 `ACTIVE_WORK.md` both read `IN_PROGRESS / S11-WX010`. No audio extraction, model execution, or WX010 experiment artifact had started at registration. Before inference, a private protocol must freeze the exact 60-second cores, 5-second bounded context, 60-second hop, sample/core mapping, deterministic selection seed/strata, conditions, time origins, manifest format, output ownership and conflict treatment, resource gates, and retry/resume logic.

The approved target is `/home/teddy/stage11-whisperx-ab-private/analysis/S11-WX010/` on VM122. WX007–WX009 evidence and model snapshots are to be verified and reused only when their source/configuration hashes match. Keep Qwen and Whisper Worker active; each new model workload requires at least 4096 MiB free VRAM and 6144 MiB available RAM. No model execution or production change is recorded at registration. This entry records authorization and pending gates, not completed evidence or product quality.

## 2026-10-15 — S11-WX009 listening comparison and closure

S11-WX009 continued from `READY_FOR_USER_REVIEW / S11-WX009` at canonical base `ea96bf893d34f295f7daf4e502173e8969426612`. The supplied chat attachment was independently identified by its stated byte hash: `/tmp/S11-WX009-listening-judgments.json` on the `downloader` host measured 2,290 bytes and SHA-256 `9d3f977e1083037718e0ea24ed1e4930241cd9e652d9e33aad44b40526ae5ebe`. This proves byte identity to the user-provided attachment hash; it does not prove that `downloader` is VM108. The JSON passed schema, task/review type, four unique window/variant pairs, interval, source hash, and field-format checks. It was copied without modification over the existing strict-host-key SSH/SFTP path to VM122 account `teddy` (`local-llm`) at `/home/teddy/stage11-whisperx-ab-private/review/S11-WX009/S11-WX009-listening-judgments.json`; destination size and SHA match, owner is `teddy:teddy`, and mode is `0600`. The raw JSON was not added to Git.

### User listening and existing diarization

| Window | Independent listening (both inputs) | Original pyannote | Demucs pyannote | Comparison |
|---|---|---|---|---|
| B-early-JA, 00:01:34.575–00:02:04.575 | 2 distinct voices; approximate changes at 15, 20, 23 s; speech; high confidence | 3 speakers, 13 turns, 4 changes at 9.835, 15.488, 20.399, 23.673 s | 2 speakers, 17 turns, 9 changes at 4.790, 4.807, 7.253, 8.030, 8.857, 8.873, 15.539, 20.450, 23.690 s | Demucs count matches the listener and its last three changes are near the listener's approximate times, but it adds several early switches. Original has one additional speaker label and a change near 9.84 s not reported by the listener. |
| B-middle-JA, 01:03:33.601–01:04:03.601 | 2 distinct voices; change time unknown; speech and moan; high confidence | 1 speaker, 6 turns, 0 changes | 2 speakers, 6 turns, 1 change at 23.268 s | Demucs count matches. The user did not time the change, and the moan is not independently time-labeled, so the split cannot be attributed to a second speaker rather than vocalization/model behavior. |

The two-window listener count agrees with Demucs in both windows, but this is not speaker-accuracy or DER verification. In B-early, the Demucs turn list includes very short switches around 4.79–8.87 s; whether those are true turns is unresolved. The user-reported times are approximate, not frame-level boundaries. In B-middle, original diarization may have merged voices while Demucs may have split a voice or assigned a moan differently; the saved evidence cannot decide which. Speaker IDs remain local to each window. Both standard and exclusive diarization summaries agree on counts/turn counts, but that agreement is not a gold label.

### Saved WhisperX linkage

The existing eight WX007 candidates (two VAD settings × two audio variants × two windows) were reused and their output hashes matched the WX008 cross-references. Each condition produced one broad candidate segment spanning almost the entire 30-second window: approximately 1.67–30.00 s for B-early and 1.79–30.00 s for B-middle. B-early assignments are `AMBIGUOUS` in all four conditions because each candidate spans multiple diarization speakers. B-middle original-audio assignments are mechanically `SUCCESS` in two conditions because only one predicted speaker intersects the broad interval; Demucs assignments are `AMBIGUOUS` in two conditions because two speakers intersect it. `SUCCESS` here does not establish transcript or speaker correctness. All eight target candidates are present; no no-candidate case occurred in these windows. WX007/WX008 previously recorded an original-audio `clip-020` onset-0.50 case with no candidate, so diarization output alone must never be treated as evidence that dialogue exists. Japanese transcript accuracy, exact speaker assignment, non-speech attribution, and DER remain `UNKNOWN`.

### Proposed FNS-247 whole-title isolated evaluation — requires separate approval

This is a proposal only; no full-title processing occurred. FNS-247 is 02:54:20.40 (10,460.4 s). Use the existing 313-cue JA index only as a mapped time-coverage reference: preserve raw JA times separately from the frozen affine video mapping (`video_ms = raw_ms * 1.0141571005475907 + 239.121464`, 40/40 anchors, median absolute residual 219 ms). A JA gap is not evidence of no speech; external JA is not word-level gold.

Freeze these comparisons before any future output is viewed: WhisperX 3.8.6 / large-v3, Japanese, float16, batch 1, beam/best-of 5, temperature 0, no prompt/hotwords, Silero 30-second VAD chunks, offset 0.363; four conditions are original/VAD onset 0.50, original/onset 0.45, Demucs vocals/onset 0.50, Demucs vocals/onset 0.45. Reuse Demucs 4.1.0 `htdemucs` vocals, segment 7 s, one shift, overlap 0.25; validate sample count, duration, channel/rate conversion, and source time origin for every chunk. Run pyannote.audio 4.0.7 Community-1 at pinned revision `3533c8cf8e369892e6b79ff1bf80f7b0286a54ee` on original and Demucs inputs, retaining regular and exclusive outputs. Keep all other model/decode settings fixed.

Proposed chunking default: 60-second ownership cores with 5 seconds of context on either side (70-second input except at title edges), 60-second hop, about 175 cores. Freeze start offset, edge ownership, and duplicate handling before inference. Assign candidate/turn records to one core by their midpoint while preserving all overlap-region disagreements for boundary review; do not silently deduplicate conflicting transcripts or turns. For ASR use the existing 30-second VAD chunks within each input. Demucs output must map back to the exact source samples and video time; any length or time-origin mismatch blocks boundary claims. Pyannote speaker IDs are local to each core; do not join IDs across cores automatically. Cross-core identity remains `UNKNOWN` or `AMBIGUOUS` unless independent reference evidence supports it.

Run full-title candidate generation on all four ASR conditions, then evaluate a pre-registered stratified sample spanning early/middle/late periods, JA-cue and JA-gap times, the existing WX007 cases (`clip-007` candidate loss, `clip-008` conflict, repeats and non-dialogue candidates), and independently confirmed music/weak-speech/moan windows. Freeze sample seed and strata before viewing new model output. Compare ASR candidates with mapped JA cue coverage and gaps, but report candidate recovery separately from verified transcription. Use an independent, blinded Japanese reference sample for transcription accuracy; use an independently labeled vocalization/speech sample for false-dialogue risk; and use a time- and speaker-labeled reference subset for boundary and diarization metrics. If no reference exists, report the metric `UNKNOWN`. Evaluate repeated/overlapping text, false dialogue on music/moans, omitted speech, boundary drift, speaker merges/splits, and candidate-to-turn assignment by condition. Preserve cross-speaker STT candidates as `AMBIGUOUS` rather than forcing one speaker. No numerical product-quality thresholds are approved; the future task must set any thresholds before inference and report improvements and regressions separately. Evaluation labels are for development evidence only and do not add per-title manual review to ordinary operation.

Rough sequential compute estimate for the proposed 60-second core/5-second context scheme: about 2 h 44 min Demucs CPU, 15 min WhisperX for onset 0.45, 17 min for onset 0.50, and 9 min pyannote across original/Demucs, or roughly 3 h 25 min of model work. This is a linear extrapolation, not a runtime guarantee: WX007 measured Demucs 444.134 s over 551.376 s of sample audio (peak process RSS 1,649 MiB, no GPU); WhisperX elapsed 41.480 s for 1,102.752 s input at onset 0.45 and 30.512 s for 731.376 s input at onset 0.50 (process RSS peak about 3,930 MiB, process VRAM peak about 3,720 MiB, minimum free VRAM about 3,870 MiB); WX008 pyannote used 2.935 s original plus 1.955 s reused-Demucs inference for 106.36 s per variant (peak allocated VRAM 1,628 MiB, peak RSS 1,716 MiB). Full-title I/O, decode, load, boundary, and evaluation overhead are not included, and larger context windows may change memory and throughput.

Future safety proposal: run sequentially in a dedicated VM122 environment/cache; before each workload require at least 4,096 MiB free VRAM and 6,144 MiB available RAM, matching WX008's pre-call thresholds. Keep Qwen and Whisper Worker active; stop launching isolated work if resource headroom falls below the gate or either service is impaired, and never stop/restart a protected service. Preserve partial private results and manifests on safe abort. Do not modify NAS source, operational models, databases, services, timers, Stage11/Stage12 code, or publication targets. Keep audio, Japanese transcript, and judgments private; Git receives only hashes, protocol, and summarized results. Hermes remains the semantic interpretation/Korean translation owner and deterministic code retains cue identity, order, accepted timestamps, validation, and publication safety. The Stage11 contract's unresolved priority between a coverage-complete JA master and whole-title Hermes primary translation is outside this experiment and remains for the user to decide.

`USER_ATTACHMENT_IDENTITY=PASS`, `USER_JSON_VALIDATION=PASS`, `PRIVATE_EVIDENCE_TRANSFER=PASS`; speaker count matched Demucs in two windows, while speaker accuracy/DER and Japanese transcription accuracy remain `UNKNOWN`; `FULL_TITLE_PROPOSAL=READY`. No model run, new extraction, production change, subtitle change, NAS/Jellyfin write, or publication occurred. The router and Stage11 `ACTIVE_WORK.md` are returned to `INACTIVE / TASK_ID NONE`. Any whole-title evaluation requires separate user approval and a new registered Stage11 task.

## 2026-10-15 — S11-WX009 independent speaker listening package ready

S11-WX009 was registered from canonical base `5363b0c96fc98d03003c1ff951f8fbb9b1922f74`; registration commit `f6b5237877a305276c7924cda31628eacbdabd26` was confirmed on `origin/teddy-subtitle-stage11`. The router and Stage11 `ACTIVE_WORK.md` both now read `READY_FOR_USER_REVIEW / S11-WX009`. The approved scope is limited to independent listening for two existing WX008 windows and a later proposal; the whole-title experiment is not authorized by this task.

The two existing source windows were verified without extraction or inference: `B-early-JA` video 00:01:34.575–00:02:04.575 and `B-middle-JA` video 01:03:33.601–01:04:03.601. Each original WAV and reused Demucs vocal WAV is 30 seconds, 16 kHz mono, 480,000 frames. All four file hashes match WX008's frozen selection manifest; the Demucs input SHA and verified time origin match the corresponding original. WX008 selection/run manifest SHA-256 values are `4a34eb0b2a6abfa03ef4d4c01688251739693e116bd489db5ab7905a0f1daf5a` and `7ebc670b025d691f90e2935564fe002c273d60f6e376f56d0f66532182b98409`. The WX007 selection, extraction, Demucs, WhisperX and base-reuse provenance files also match the hashes recorded by WX008. For both windows, the four saved WX007 WhisperX output files (original/Demucs × VAD 0.45/0.50) match their referenced hashes, and all WX008 cross-links match; the four WX008 diarization result files likewise match their run manifest. The private manifests preserve detailed paths and output hashes.

The offline review archive is `/home/teddy/stage11-whisperx-ab-private/review/S11-WX009/S11-WX009-listening-review.zip`, SHA-256 `5a9ca4e07f8bba3f55c47ec97a369359750fce3ab5d77c97f00ad069feb594c8` (5,039,572 bytes). It contains exactly four reused WAVs, a local HTML listening form, README, and non-sensitive provenance manifest. The page permits alternating playback, records voice count including `UNKNOWN`, approximate change times, vocalization kinds, uncertainty, and optional notes. It does not include pyannote predictions, Japanese transcript, or model hypotheses and has no external network requests. VM122 review storage is private (`0700` directory; `0600` files/archive). No user judgment has been fabricated or added.

`SOURCE_EVIDENCE=PASS`, `TARGET_WINDOWS=2/2`, `OFFLINE_REVIEW_PACKAGE=READY`, `USER_LISTENING=PENDING`. No new audio extraction or model run occurred (`MODEL_RUNS=0`); production changes and NAS/Jellyfin writes remain zero. Next: the user retrieves and listens to the ZIP, then submits the exported `S11-WX009-listening-judgments.json`. Only after that judgment will WX009 compare the existing pyannote/STT evidence and prepare a proposal for separate approval of any FNS-247 whole-title isolated experiment. No whole-title run or production integration is authorized.

## 2026-10-15 — S11-WX008 FNS-247 speaker diarization completed

S11-WX008 was registered, blocked at the initial model-access check, then resumed under the same task ID after the user made a Hugging Face token available directly on VM122. The blocked-state commit `83bf9eededc362e2619630860856de55663ddb2d` and resume commit `cd67cbaf7c2e3c4e82ae5c77d972a9173c351de0` were confirmed on the canonical remote before execution. The token file was owned by `teddy`, mode `0600`, and readable. Authenticated access to the gated Community-1 repository returned all 10 files at revision `3533c8cf8e369892e6b79ff1bf80f7b0286a54ee`; the token was never printed, copied to CT108, or stored in Git. No terms were accepted on the user's behalf. The [official model card](https://huggingface.co/pyannote/speaker-diarization-community-1) describes the gated conditions and local pyannote.audio pipeline.

The isolated VM122 environment used `pyannote.audio 4.0.7`, `torch 2.8.0+cu128`, `torchaudio 2.8.0+cu128`, and the TorchCodec 0.7.0 CPU decoder. The latter avoided an NPP symbol conflict from the CUDA decoder; model inference itself ran on the RTX 3060. The existing private FFmpeg 7.1.5 prefix was referenced read-only. Model assets were downloaded to a WX008-only cache, then loaded from the pinned local snapshot with Hugging Face offline mode and pyannote telemetry disabled.

The pre-output selection reused three existing WX007 JA-indexed windows—one each from the early, middle, and late thirds—and the WX005 user-reviewed `clip-020` mixed-vocalization window. The latter's user review covered core audio only; its surrounding context was not listened to. Raw JA timestamps and affine-mapped video timestamps remain separate in the private protocol. Four windows total 106.36 seconds, with no interval overlap. The four original WAVs and four saved WX007 `htdemucs` vocal stems were hash-verified, mono 16 kHz, and equal in frame count, duration, and time origin. No audio was newly extracted and Demucs was not rerun.

### Diarization and saved STT linkage

| Window (video time) | Original speakers / turns / changes | Demucs speakers / turns / changes | Overlap pairs |
|---|---:|---:|---:|
| B-early-JA 00:01:34.575–00:02:04.575 | 3 / 13 / 4 | 2 / 17 / 9 | 0 / 0 |
| B-middle-JA 01:03:33.601–01:04:03.601 | 1 / 6 / 0 | 2 / 6 / 1 | 0 / 0 |
| clip-020 01:54:11.220–01:54:27.580 | 1 / 12 / 0 | 1 / 14 / 0 | 0 / 0 |
| B-late-JA 02:03:31.597–02:04:01.597 | 1 / 7 / 0 | 1 / 4 / 0 | 0 / 0 |

The regular and exclusive outputs had matching speaker and turn counts in all eight runs. No output contained a cross-speaker overlap interval; this does not establish that the audio had no overlap, and the selected set had no independent overlap-labeled window. Across selected windows, diarization turns shorter than one second numbered 27 on original audio and 32 on Demucs vocals. In `clip-020`'s user-reviewed core, five original and seven Demucs turns carried a single temporary speaker label; this is a possible non-speech assignment risk, not a confirmed false speaker.

Saved WX007 candidate-to-speaker intersections were evaluated independently for regular and exclusive output. Original-audio outputs had 7 candidate segments: 5 `SUCCESS`, 2 `AMBIGUOUS`, 0 `FAILURE`; one additional original `clip-020` onset-0.50 condition had no candidate. Demucs outputs had 8 candidate segments: 4 `SUCCESS`, 4 `AMBIGUOUS`, 0 `FAILURE`. Exclusive counts matched these results. The long WX007 candidate intervals often spanned most of a 30-second window, so `SUCCESS` means only that one diarization label intersected the interval; it does not verify that the transcript or speaker assignment is correct. Candidate linkage by window: early original 0/2 success and 2/2 ambiguous, Demucs 0/2 and 2/2; middle original 2/2 and 0/2, Demucs 0/2 and 2/2; late both variants 2/2 success; `clip-020` original 1/1 candidate success plus one no-candidate condition, Demucs 2/2 success.

Japanese transcript truth, speaker accuracy, and DER remain `UNKNOWN` without independent gold. Speaker counts changed between original and Demucs in the early and middle windows; no merge/split direction can be confirmed without speaker truth. The selected sample is small and does not prove full-title readiness or the no-per-title-review product goal. `FULL_TITLE_READINESS` is `추가 검증 필요`.

Inference took 2.935 seconds total on original inputs and 1.955 seconds on reused Demucs inputs; local model load took 0.542 seconds. Pyannote peak CUDA allocation was 1,628.48 MiB, process peak RSS was 1,716 MiB, minimum observed free VRAM was 5,340 MiB, and minimum available RAM was 7,155 MiB. Qwen PID 1005 was active before and after every call and at final verification; no service was stopped or restarted. Inference ran offline with telemetry disabled.

Private VM122 artifacts remain under `/home/teddy/stage11-whisperx-ab-private/analysis/S11-WX008`, outside Git. Source provenance: FNS-247 media SHA-256 `442e19dd0c45df924ecac28c76f4b3c18b19f53f0e5a00e3abd76bb650a84651`; WX007 JA time-index SHA-256 `b63745df3a9bfa3f7ec895b289c12d6b069f7e8d2024355e13e24c63ef21d270`; WX005 user core-only revision SHA-256 `3d52da305de22e816e1426f1823477e02cd029242c8b5e3e19a608f471487dff`. Evidence SHA-256: frozen protocol `2f723de23dc3f06893970cf84c60658fd2a149b3ad1c55d09f85622298a8bc10`; selection manifest `4a34eb0b2a6abfa03ef4d4c01688251739693e116bd489db5ab7905a0f1daf5a`; model snapshot manifest `272eb05c8df4b94dabd3f965855ffb3c4d24af686d6943504ebd3efd6743b346`; package lock `345e9c8eaeaf0b97fa3aaa8c69ae4bbdf9b76e201eba2bdaab0d96673da861dc`; run manifest `7ebc670b025d691f90e2935564fe002c273d60f6e376f56d0f66532182b98409`. All eight output hashes matched their run manifest. No WhisperX run, transcription, other-title test, full-title processing, production change, NAS/Jellyfin write, or publication occurred. The router and Stage11 active-work file are returned to `INACTIVE / TASK_ID NONE`.

Next: the user decides separately whether further isolated FNS-247 diarization validation is warranted. This experiment does not authorize full-title runs or production integration.



## 2026-10-15 — S11-WX008 resumed after authenticated model-access check

The user made the Hugging Face token available directly on VM122 at
`/home/teddy/.config/stage11-wx008/hf-token`. Read-only verification as `teddy`
confirmed a regular, readable file owned by `teddy` with mode `0600`. Its value
was not printed, copied to CT108, or committed. Authenticated Hugging Face Hub
checks returned gated model metadata and access to all 10 repository files for
`pyannote/speaker-diarization-community-1` at revision
`3533c8cf8e369892e6b79ff1bf80f7b0286a54ee`. This verifies effective account
access to the gated files; no terms were accepted in this session and no access
control was bypassed.

The router and Stage11 active-work file were both changed from
`BLOCKED / S11-WX008` to `IN_PROGRESS / S11-WX008` and must be validated and
confirmed on the canonical remote before installing a package, creating
experiment files, downloading model files, extracting audio, or running a
model. `pyannote.audio` remains absent from the previously inspected isolated
environments. No model execution or experiment artifact has started.

## 2026-10-15 — S11-WX008 FNS-247 speaker diarization BLOCKED at model access

S11-WX008 was registered on the canonical `teddy-subtitle-stage11` branch at
`bebf75a97ba7c9ed3bc4679925d7b532ba68b204`. Registration checks passed and the
activation commit was confirmed on the remote before model or audio work. The
router and Stage11 active-work record now both retain `S11-WX008` with status
`BLOCKED`; the task is not closed because its approved model-access prerequisite
is unresolved.

Read-only access checks on VM122 found no Hugging Face token available to the
designated isolated environment. The official
`pyannote/speaker-diarization-community-1` model is gated and requires the
account holder to accept its access conditions. No terms were accepted on the
user's behalf and no access control was bypassed. The inspected Stage11
environments do not have `pyannote.audio` installed, and no separate diarization
environment or experiment cache was created while access was blocked.

The VM122 preflight observed 8,390 MiB available RAM and 7,595 MiB free GPU
memory on the 12 GiB RTX 3060; the existing Qwen `llama-server` remained active
at PID 1005. These are preflight readings only. No model was loaded or run.
Because the access gate failed before selection was frozen, zero windows were
selected, no audio was extracted, and no protocol manifest or diarization
outputs were created. Original and Demucs diarization, speaker counts/turns,
WhisperX-speaker linkage, and overlap evaluation are all `NOT_RUN`; speaker
accuracy and DER remain `UNKNOWN`. No inference resource cost was incurred.

Result: `S11_WX008_REGISTRATION=PASS`, `MODEL_ACCESS=BLOCKED`,
`ISOLATED_ENVIRONMENT=BLOCKED` for execution, `SELECTED_WINDOWS=0`,
`ORIGINAL_DIARIZATION=NOT_RUN`, and `DEMUCS_DIARIZATION=NOT_RUN`.
`FULL_TITLE_READINESS=판단 불가`. Production changes, full-title processing,
NAS/Jellyfin writes, and publication writes were zero. No model, audio, private
Japanese text, or credentials were added to Git.

Resume only after the user has accept…188220 tokens truncated…bf80f7b0286a54ee`. Model execution cost was about 25m59s wall time. WhisperX per-core processing sums were 176.575, 180.086, 193.398, and 197.245 seconds; minimum observed free VRAM was 3,440 MiB, minimum available RAM 7,392.6 MiB, and peak process RSS about 3,943.5 MiB. Pyannote processing sums were 326.586 seconds original and 298.150 seconds Demucs; minimum free VRAM was 5,412 MiB, minimum available RAM 7,826.9 MiB, and peak process RSS about 1,705 MiB. The controller calls the frozen 4,096 MiB VRAM / 6,144 MiB RAM gate before each workload; all six completed. Qwen remained active in recorded resource samples. Demucs had been processed before the full run and was reused; its earlier cost is not part of these controller timings.

`R5_EXTRACTION_MANIFEST_PROVENANCE=UNRESOLVED` remains unchanged: historical manifest SHA-256 `05c701eb7dbb71006b8321472c9da2dd2387ee6a0f6ea81c483c18bf9e892e69`, current manifest SHA-256 `14f2fdcee2840ff58dd060a778ab489c84f354a8983908e7678c99f2e4ee2050`. Japanese transcription accuracy, false-dialogue accuracy, speaker accuracy/DER, and boundary accuracy are `UNKNOWN`; product quality is `INCONCLUSIVE`. Production changes, NAS/Jellyfin writes, and subtitle publication are 0. This verification performed no model reruns, audio extraction, Demucs reruns, Hermes work, or subtitle generation.

The approved S11-WX010 evaluation and its reporting criteria are complete. The router and Stage11 `ACTIVE_WORK.md` are now `INACTIVE / TASK_ID NONE`; the approved Stage11 design contract remains `APPROVED`. Any next evaluation or product work requires a separately approved Stage11 task. The next decision is whether to register work that adds independent Japanese transcript, speech/non-speech, and speaker-time references for stronger quality measurement.

### 2026-10-17 — S11-WX011 S04–S16 user listening comparison and S03 timing check

The canonical task remained `IN_PROGRESS / S11-WX011` at `6c319ccd2aec2130c3510c8dce33a92f5ed80481`. The fixed S11-WX011 sample manifest SHA-256 remains `3b4ac21598d3a8f7e01588a760a0b6f88644d3100519705f789641616abbf478`. Read-only checks verified all 16 listening WAVs, 28 referenced original/Demucs source-core files, the six WX010 condition manifests, and 112 referenced condition/core output files. Source, core, lock, output hashes, and audio/video timestamp mappings passed; maximum mapping delta was 0 ms. No existing WX010/WX011 artifacts were modified.

The user's S04–S16 notes were preserved verbatim in the private VM122 archive `/home/teddy/stage11-whisperx-ab-private/analysis/S11-WX011/comparisons/S04-S16-user-listening-wx010-20261016T152030Z/`. Listening time, confidence, and model-exposure status were not supplied, so this pass is not claimed as strictly blind. The notes indicate speech in 10 windows and nonverbal vocalizations without reported speech in 3. Korean phonetic impressions remain auxiliary listening evidence, not Japanese transcription truth.

In Original .50 / Original .45 / Demucs .50 / Demucs .45 order, candidate-occurrence counts across S04–S16 were 15/15/17/17. Candidate presence was 9/13 in either Original condition and 11/13 in either Demucs condition; it was present in 7/10 versus 8/10 speech-noted windows and 2/3 versus 3/3 vocalization-only notes. Two Demucs-only windows include one speech-noted window and one moan-noted window; two speech-noted windows had no candidate in any condition. Candidate presence is not confirmed recovery or confirmed false dialogue. VAD .45 changed no candidate counts; interval positions changed in 1 Original window and 3 Demucs windows. Five windows had time-overlapping output spans from neighboring cores; exact same-text duplication was not scored.

Exclusive pyannote core-local speaker counts differed between Original and Demucs in 4/13 windows; turn counts and regular/exclusive representations also varied. These are output differences, not speaker accuracy. The separate S03 check found existing candidate intervals ending by approximately 4.60 s while the reported Gemini estimates place starts around 5 and 7 s. The user did not confirm those times, so this remains a possible gap only. Japanese transcription accuracy, false-dialogue accuracy, exact boundaries, and speaker DER remain `UNKNOWN`; product quality remains `INCONCLUSIVE`. `R5_EXTRACTION_MANIFEST_PROVENANCE=UNRESOLVED`.

No model inference, audio extraction, Demucs rerun, Hermes execution, production change, NAS/Jellyfin write, or subtitle publication occurred. S11-WX011 remains `IN_PROGRESS / S11-WX011`. If another bounded review is useful, the next most useful evidence is approximate in-WAV timing for the speech-noted windows that had no candidate in any condition; S03 4.5–7.5 s is an optional follow-up, not a verified miss.


### 2026-10-16 — S11-WX011 independent Japanese audio accuracy evaluation registered

The user approved a bounded Stage11 evaluation of up to 16 short windows using completed S11-WX010 outputs. The scope is to verify independent reference provenance, freeze a reproducible sample, measure only dimensions supported by actual references, and report uncertainty and regressions. Existing WX010 outputs, models, locks, and source evidence are read-only. Model execution, audio extraction, Demucs reruns, translation, subtitle work, and production/publication changes are prohibited. No private WX011 evaluation artifact is to be created until this registration is confirmed from the canonical remote. The next checkpoint is independent verification of WX010 evidence and reference availability before freezing a sample.

### 2026-10-16 — S11-WX011 frozen sample and partial independent-reference evaluation

The S11-WX011 registration was read back from canonical commit `dd9a738d684bba1e3d71388b4782932dd1c92631`. Existing WX010 evidence was reused read-only; its preceding independent audit verified 1,050/1,050 outputs with 0 missing or invalid. The FNS-247 source identity, R6 locks, frozen 175-core plan, four WhisperX manifests, two pyannote manifests, 313-cue JA index, WX005/WX007/WX009 review evidence, and relevant selected input/output files were hash-checked. The historical/current R5 extraction-manifest SHA discrepancy remains `UNRESOLVED`.

The frozen selection protocol SHA-256 is `73f77e4852f187faf1ee87e68a9fb99b6bfb39ee59b09830098fc0048c694325`; the private, non-overlapping sample manifest SHA-256 is `3b4ac21598d3a8f7e01588a760a0b6f88644d3100519705f789641616abbf478`; the private safe aggregate SHA-256 is `bf57c2ecd1ba44bac36603136bac9cd2917a8d210d16e23fb41c978cf9c2457e`. It contains 16 windows: 3 JA-overlapping candidates, 3 JA-gap candidates, 3 user-labeled non-dialogue windows, 3 speaker/boundary diagnostics, and 4 WX007 regression sentinels. Owner-core clipping yielded 188.613 seconds total; the approximate 4–8 minute planning target was not met, and no windows were extended after selection.

Independent references are partial: Japanese transcript references 0/16; speech-presence labels 10/16 (7 speech-present and 3 non-dialogue); window-level speaker-count judgments 2/16; exact boundary references 0/16. WX005 user labels were confirmed as core-only listening, with confidence not provided and model-hypothesis exposure not attested by the export. WX009 contains high-confidence first-pass judgments, and its review manifest states that model hypotheses/transcripts were not included. WX009 gives two distinguishable voices for both diagnostic windows; approximate change times are available only for B-early and are not exact boundaries.

Across the 16 selected windows, candidate interval counts were 20/20/23/23 for original/VAD 0.50, original/VAD 0.45, Demucs/VAD 0.50, and Demucs/VAD 0.45. Candidate presence overlapped 4/7 speech-labeled windows in each original condition and 5/7 in each Demucs condition. It overlapped 2/3 non-dialogue-labeled windows in each original condition and 3/3 in each Demucs condition. These are small-sample interval-presence and false-dialogue-risk indicators, not verified transcripts or confirmed hallucinations. The two VAD thresholds had identical candidate counts in all 16 windows. WX007 clip-003 remained candidate-free across all conditions; clip-005/006 had candidates in all four; clip-008 had candidates only in the Demucs conditions. Candidate presence is not proof of accurate restoration.

For the two WX009 speaker-count windows, the user's count was 2 in each. Existing WX008 Demucs output counted 2 in both, while original output counted 3 for B-early and 1 for B-middle. This is limited agreement on two windows only. WX010 per-core context speaker counts cannot be merged across core-local IDs or scored against a window-level count. Japanese transcript accuracy, exact boundary accuracy, and speaker accuracy/DER remain `UNKNOWN`; product quality is `INCONCLUSIVE`.

No inference, audio extraction, Demucs rerun, Hermes execution, production change, NAS/Jellyfin write, or subtitle publication occurred for WX011. WX011 remains `BLOCKED / S11-WX011` because no independent Japanese transcript or exact speech/speaker-time reference exists for scoring transcription accuracy. The next decision is whether to provide or authorize an independent Japanese reviewer to produce blind references for the frozen windows. No private audio or Japanese transcript text is included in this handoff.

### 2026-10-16 — S11-WX011 blind listening package authorized

The user approved a limited blind-listening evidence package because no Japanese-speaking reviewer is available. WX011 remains the same task. The existing 16-window sample manifest is frozen at SHA-256 `3b4ac21598d3a8f7e01588a760a0b6f88644d3100519705f789641616abbf478`; no window may be added, extended, or replaced. The package will use exact frame ranges from already verified WX010 original WAVs only. No MP4 extraction, ASR, Demucs, or other model execution is authorized.

The user may independently note whether speech is audible, approximate distinct voice count and relative change times, confidence, and Korean phonetic impressions. Korean phonetic notes are auxiliary listening evidence, not Japanese transcript truth; they do not support CER/WER, Japanese transcription accuracy, DER, or product-quality PASS. The user-facing package must omit model transcripts, external Japanese subtitles, predicted speaker counts, and answer hints. A separate private mapping will preserve sample IDs/times and source-frame provenance. After package creation, request first-pass listening for S01–S03 only; preserve submitted entries before any comparison. No private audio or mapping is included in Git. At this checkpoint, package generation is pending canonical readback.

### 2026-10-16 — S11-WX011 blind listening package prepared

The canonical router and Stage11 active record were read back as `IN_PROGRESS / S11-WX011` at `fbb183f026d3773c49d9e2b4773e1eae5d7406b2` before creating the package. The frozen sample manifest SHA-256 remains `3b4ac21598d3a8f7e01588a760a0b6f88644d3100519705f789641616abbf478`; the WX010 core plan and extraction manifest were read-only inputs. All 16 windows were cropped as exact PCM frame ranges from 14 verified original WX010 WAVs; total audio is 188.613 seconds. A second pass verified each output SHA, frame count, audio format, time mapping, and byte-for-byte PCM equality with the selected source range. All 16 source references passed SHA and manifest checks, and original files were rehashed after copying.

The user-facing folder is `/home/teddy/stage11-whisperx-ab-private/analysis/S11-WX011/blind-listening-package-v1/user-facing/`. It contains only `S01.wav`–`S16.wav`, a blank 16-row listening CSV, and Korean instructions that ask for S01–S03 first. It contains no ASR output, JA subtitle, predicted speaker count, mapping, or answer hint. The separate private provenance/mapping SHA-256 is `c28a02c0f8615d61cb73bd525e3d5469fd87725e0148a624389a1ca511aa97f7`; package summary SHA-256 is `4c556b42d6c47e54aed94b847023f557247c0202a80c052ac6e4549955a3113d`. No audio or private mapping was added to Git. User listening is pending; Japanese transcript truth remains unavailable, and Korean phonetic notes will not be scored as Japanese transcription.

No model execution, audio extraction from video, Demucs rerun, Hermes execution, production change, NAS/Jellyfin write, or subtitle publication occurred. S11-WX011 remains `IN_PROGRESS / S11-WX011` pending the user's first-pass notes for S01–S03.


### 2026-10-17 — S11-WX011 S01–S03 user/Gemini comparison

The user provided speech-presence and voice impressions for S01–S03 after seeing Gemini’s hypotheses. The user evidence is preserved separately from the Gemini-reported hypothesis and is not labeled a strict blind review. The Korean phonetic note is not Japanese transcript truth. The raw Gemini response and Korean translation text were not supplied, so no Japanese-text or translation-semantic comparison was performed.

The frozen sample manifest remained unchanged at SHA-256 3b4ac21598d3a8f7e01588a760a0b6f88644d3100519705f789641616abbf478. Its mapping and source/core/output hashes, model revisions, parent lock, and video/audio time correspondence were rechecked read-only. S01 is the exact interval already reviewed as WX009 B-early-JA; its earlier, separate first-pass judgment was two voices with approximate changes at 15/20/23 seconds. S02 maps to core-055 and S03 to core-059. Their current listening evidence is not merged with the earlier WX009 result.

All three samples were reported to contain speech. S02 has a direct current count of three distinguishable voices (visitor man, existing man, woman), but that judgment followed Gemini exposure. S01 and S03 were described as broadly consistent with Gemini’s two-voice hypothesis; the user did not provide a separate numeric count or exact change times for either. Gemini’s relative start times remain approximate hypotheses.

WhisperX candidate output intervals intersected each sample as follows, in Original .50 / Original .45 / Demucs .50 / Demucs .45 order: S01 2/2/2/2; S02 2/2/2/2; S03 1/1/2/2. Some are overlapping outputs from neighboring core contexts. No exact same-text duplicate occurred within a condition, but overlapping candidate spans can represent duplicate or conflicting evidence; candidate counts are not utterance counts. Approximate Gemini start-point overlap was S01 3/5 Original and 4/5 Demucs, S02 6/6 in all four conditions, and S03 3/6 in all four conditions. These are temporal intersections, not recovered-speech or accuracy scores.

At S01, each VAD threshold preserved the same candidate text/time for a given input; Demucs began a candidate earlier than Original (about 1.59 s vs 5.33 s into the sample). At S02, the original short candidate’s text differed slightly by VAD threshold while the full-window candidate remained the same; Demucs outputs were unchanged across thresholds. At S03, Original text was unchanged and its endpoint extended about 96 ms at onset .45; Demucs candidate text changed across thresholds and the core-059 endpoint extended about 128 ms. Original-versus-Demucs candidate text differed in all samples. With no Japanese reference, none of these changes is classified as an improvement.

pyannote found three local IDs for both S02 inputs, matching the user’s count at window level only; the IDs cannot be assigned to the three described people. S01 spans core-001/core-002; counts were 3/2 in Original/Demucs on core-001 and 2/2 on core-002, with cross-core IDs kept separate. S03 had two IDs in both inputs; exclusive turn counts were 25 Original and 11 Demucs. S01 Demucs and S03 Original showed more rapid turn changes/fragmentation. The approximate Gemini times are not exact boundary truth.

Private detailed evidence was archived with user, Gemini, and WX010 records separated. Private artifact index SHA-256: 62b5c76c1fa1efa8c4042f457a3935e21242ec9ccb829c2c20711797d6dc9444. Japanese transcript accuracy, exact boundary accuracy, false-dialogue accuracy, and speaker DER remain UNKNOWN; product quality remains INCONCLUSIVE. R5 extraction-manifest provenance remains UNRESOLVED. This comparison ran no models and performed no extraction, Demucs, Hermes, production, NAS/Jellyfin, or publication writes. S11-WX011 remains IN_PROGRESS / S11-WX011.

### 2026-10-17 — S11-WX011 S03 later-speech listening supplement

The user reports directly listening to the S03 WAV and hearing conversation continue in its latter part (`USER_REPORTED_YES`). This report followed exposure to Gemini's analysis, so it is not strict blind evidence. Exact speech start/end times and Japanese transcription accuracy remain `UNKNOWN`. Gemini's approximate 5 s and 7 s times are model estimates, not ground-truth boundaries. Given the previously saved WhisperX candidate intervals ending by about 4.60 s, late dialogue omission is `STRONGLY_SUSPECTED, NOT_CONFIRMED`.

The new listening evidence was appended separately in the VM122 private WX011 archive at `/home/teddy/stage11-whisperx-ab-private/analysis/S11-WX011/comparisons/S03-late-speech-user-followup-20261017T013754Z/`; supplement SHA-256 `4287a4c4cabbbaa09fd12caef35c0c70dac0c59ce66c8fb47ffcaa1b9742f60f`, artifact-index SHA-256 `5015ef880f70e3bb66565e8ea197bdc1dd8765bdc218da3ac3e959ad241178d8`. The frozen sample manifest SHA remains `3b4ac21598d3a8f7e01588a760a0b6f88644d3100519705f789641616abbf478`; prior S01–S03 records and WX010 outputs were not modified. S11 and S15 remain priority cases because the user reported speech and all four existing WhisperX conditions produced zero candidates; that absence remains a risk indicator, not confirmation of omitted dialogue without independent interval/content evidence.

No model execution, audio extraction, Demucs rerun, Hermes execution, production change, NAS/Jellyfin write, or subtitle publication occurred. Japanese transcription accuracy remains `UNKNOWN`, product quality remains `INCONCLUSIVE`, and S11-WX011 remains `IN_PROGRESS / S11-WX011`.

### 2026-10-17 — S11-WX011 S04/S08/S13 saved Japanese output audit

The existing four WX010 WhisperX conditions were read from their saved private core JSON outputs; no inference was run. The WX011 frozen sample manifest and blind mapping hashes matched. The three listening WAVs, all relevant original/Demucs core input files and condition result JSONs passed SHA checks. Candidate intervals were recomputed against the frozen sample windows, and their output condition, parent lock, source core, ownership references, and audio/video timing links matched.

In Original .50 / Original .45 / Demucs .50 / Demucs .45 order, saved candidate counts were S04 1/1/1/1, S08 1/1/1/1, and S13 0/0/1/1. S04 and S08 each produced three distinct exact-text variants across the four conditions; the two S13 Demucs variants differed. Raw Japanese text remains only in the existing private WX010 outputs and was not copied to Git or this handoff. The candidate segments extend beyond the short listening windows; S04's intersecting output is from an adjacent core. Segment duration must not be treated as utterance duration.

The text-form classifications remain `AMBIGUOUS` pending the user's private text view alongside the existing clips. No candidate is labeled a hallucination or a confirmed recognition. Japanese transcription accuracy and misrecognition status remain `UNKNOWN`; product quality remains `INCONCLUSIVE`. The user has a verified read-only VM122 command that resolves the frozen sample mapping and result paths, validates SHA/lock links, and prints the unchanged stored text in the private terminal. No model, audio, or existing result was modified or rerun; production and publication changes remain 0. S11-WX011 remains `IN_PROGRESS / S11-WX011`.

### 2026-10-17 — GOV-004 Downloader non-subtitle workstream registered and closed

The user approved GOV-004 to register and approve a separate non-subtitle Downloader workstream. The canonical base was `45981e12f405e56498fc72f3f2d6ddc9cc740e0d`; GOV-004 was checked as unused before registration. The completed GOV-003 record remains the 2026-10-16 Stage11 contract state-paragraph alignment task and was not changed or reused. GOV-004 was first registered as `IN_PROGRESS` in the Governance router and Governance ACTIVE_WORK, validated with the governance task preflight, and published/read back at `d64da2011c33b2b1f7f9c9d46355145025dbb278` before applying the approved Downloader registration.

The canonical router now registers `downloader` with its own v1.0.0 contract and ACTIVE_WORK file. The contract is `APPROVED` and requires MP4 remux/conversion to execute globally one job at a time, independently of configured download concurrency; changing this policy requires explicit user approval. The Downloader workstream is `INACTIVE / NONE`; DL-001 remains a proposal and was rejected by the inactive-task preflight. Governance was restored to `INACTIVE / NONE`. Stage11 remains `IN_PROGRESS / S11-WX011`, with its contract and ACTIVE_WORK unchanged.

Final validation passed: all-workstreams structural governance check, governance smoke (21/21), Stage11 S11-WX011 preflight, expected DL-001 rejection, and `git diff --check`. Only governance routing/history, the new Downloader contract/ACTIVE_WORK, and this handoff were changed. No product code or runtime changed; no download retries, data deletions, Docker or Proxmox changes, NAS/Jellyfin writes, or deployment occurred. GOV-004 is closed; DL-001 requires a separate user-approved registration.

### 2026-10-17 — DL-001 shared registration and Governance closure

The user approved registering DL-001 as a shared Governance+Downloader task for registration only. The shared registration was published and read back at `eebe6a22f2d102e85e4638c21a91f0a1189c4c4e`; both router entries and ACTIVE_WORK files showed `IN_PROGRESS / DL-001` with `REQUIRES_WORKSTREAMS: governance,downloader`. Shared task preflight, all-workstreams structural validation, Stage11 S11-WX011 preflight, governance smoke (21/21), and `git diff --check` passed before and after readback.

After successful shared readback, Governance was closed as `INACTIVE / NONE` and Downloader remains `IN_PROGRESS / DL-001` with `REQUIRES_WORKSTREAMS: downloader`. The Downloader v1.0.0 APPROVED contract and DL-001 scope are unchanged. Stage11 remains `IN_PROGRESS / S11-WX011`. This registration phase changed no product code, production files, services, real download jobs, NAS/Jellyfin data, or user data; it performed no retries, recovery, or deletions. Product implementation is not part of this registration-only phase.

### 2026-10-19 — GOV-005 Discovery Writer Safety workstream registered and closed

The user approved GOV-005 to register the independent `discovery-writer-safety` workstream. The canonical base SHA was `30fb83e1c6b2a80eee67cef5bac8192bf6fa719b`. Governance was activated as `IN_PROGRESS / GOV-005` and read back at `68d25dc2626ea3edd687925dea85565102283fd7` before registration. The new workstream was then registered and read back at `33432e965292610e3cfe3f909438ec2fe5fe588b` with contract `1.0.0 / APPROVED` and ACTIVE_WORK `INACTIVE / NONE`. Its route is limited to Discovery Writer Unix socket lifecycle and stale-socket safety; other non-subtitle Discovery remains in Downloader.

Final checks passed: all-workstreams structural validation, Governance smoke (21/21), Downloader `DL-001` preflight, Stage11 `S11-WX011` preflight, and `git diff --check`. The inactive `DWS-001` preflight was rejected as expected. GOV-005 was closed and Governance restored to `INACTIVE / NONE`. Downloader remains `IN_PROGRESS / DL-001`; Stage11 remains `IN_PROGRESS / S11-WX011`. Their contract and ACTIVE_WORK files were not changed. No product code, Writer smoke, Docker build, production service, socket, database, download, NAS/Jellyfin, or user data was changed. DWS-001 remains inactive and needs separate task activation approval.
