# Stage11 — WX011 frozen 16-window evidence and uncertainty scorecard (2026-11-12)

**Classification:** `DOCUMENTARY_SNAPSHOT / CANONICAL_SUMMARY_BASED / PRIVATE_SOURCE_REFRESH_NOT_RUN`  
**Workstream:** `stage11` · **approved task:** `S11-WX011 / IN_PROGRESS` · **contract:** `1.0.0`  
**Branch:** `teddy-subtitle-stage11` · **baseline canonical HEAD:** `e9e37df6c1575f772e1577b795fa437c64484197`

## Purpose and counting rules

This is a **read-only synthesis of the existing canonical Stage11/WX011 evidence**; it is not a new model evaluation or an independent recheck of private VM122 files. Preserve the original frozen 16 samples, their original labels, and all historical denominators. One overlapping WhisperX segment is **not** one verified spoken sentence. A human speech-presence report is **not** a Japanese transcript. Do not substitute non-blind follow-up observations for independent references.

## Frozen sample / evidence integrity

| Measure | Recorded result | Interpretation |
|---|---:|---|
| Frozen windows | **16**, non-overlapping, **188.613 s** | No new selections |
| Sample categories A/B/C/D/E | **3 / 3 / 3 / 3 / 4** | Stratified, **not representative** of all films |
| WX010 independently audited outputs | **1,050 / 1,050** | Stored output integrity, **not** ASR accuracy |
| WX011 blinded listening WAVs | **16 / 16** source-frame/SHA checks historically PASS | WAV integrity, **not** verified dialogue |
| Sample manifest SHA-256 | `3b4ac21598d3a8f7e01588a760a0b6f88644d3100519705f789641616abbf478` | Historical pin; **not re-read on VM122 in this scorecard** |
| R5 extraction-manifest provenance | **UNRESOLVED** | Do not upgrade source provenance to PASS |

## Independent reference coverage — denominator is 16 frozen windows

| Reference type | Availability | What is **not** established |
|---|---:|---|
| Independently verified Japanese transcript truth | **0 / 16** | WER/CER, translated meaning, actual Japanese wording |
| Speech-presence reference labels | **10 / 16**: 7 speech, 3 non-dialogue | No complete 16-window independent speech truth |
| Window-level speaker-count references | **2 / 16** | Speaker identity and speaker DER |
| Independent exact utterance boundaries | **0 / 16** | Exact speech start/end or full omission coverage |

These reference labels predate the latest user follow-ups. Keep them distinct from later user listening reports and model candidate intervals.

## Saved WhisperX candidates — denominators must not be mixed

Four saved conditions: original/VAD .50, original/VAD .45, Demucs/VAD .50, Demucs/VAD .45 (in that order).

| Historical measure | Original .50 | Original .45 | Demucs .50 | Demucs .45 |
|---|---:|---:|---:|---:|
| Candidate **occurrences** overlapping the 16 frozen windows | 20 | 20 | 23 | 23 |
| Speech-reference windows with at least one overlapping candidate | 4/7 | 4/7 | 5/7 | 5/7 |
| Non-dialogue-reference windows with at least one overlapping candidate | 2/3 | 2/3 | 3/3 | 3/3 |

The 7/3 denominators apply **only to the independent 10-window speech-presence reference subset**, not all 16. The 20/23 entries are overlapping segment **occurrences**, not unique utterances, transcript recoveries, or confusion-matrix counts. A lower VAD threshold (.45) did not change the saved 16-window occurrence totals.

**Separate user-listening reporting cohort:** S01–S03: user-reported speech in 3/3, after model-hypothesis exposure; S04–S16: user-reported speech in 10/13 and non-dialogue/vocalization in 3/13, with exposure/blinding status not attested. These are descriptive listening reports, not a new independent 16-window reference set. Preserve the historical 13-window candidate-presence counts (**9/13 original, 11/13 Demucs**) separately from the 7/3 independent-reference subset.

## Two distinct quality-risk groups — descriptive, not verified error cases

| Frozen cases | Risk | Grounded evidence | Decision |
|---|---|---|---|
| **S03** | Possible missed later dialogue | User reported continuing speech in the later part after candidate output ending about 4.60 s; timing impression followed model exposure | **STRONGLY_SUSPECTED / NOT_CONFIRMED**; exact independent boundaries unavailable |
| **S11, S15** | Possible unrecognized speech | User-reported speech, zero overlapping candidates in each of four frozen conditions | **OMISSION_RISK / UNCONFIRMED** without independent reference |
| **S04, S08** | Context-wide Japanese text may contaminate a short non-dialogue clip | One saved candidate per condition, extending well beyond the short WAV; S04 is from adjacent processing core | **POTENTIAL_SUBTITLE_CONTAMINATION**, not confirmed hallucination |
| **S13** | Demucs-only candidate on non-dialogue-reported clip | No original-condition candidate; one candidate in each Demucs condition with different text surfaces | **POTENTIAL_SUBTITLE_CONTAMINATION**, not confirmed hallucination |

S04/S08/S13: user's later, model-exposed short-WAV follow-up reported no clear dialogue in all **3/3**. Historical first-listening reports are **coarsely consistent in 3/3**; this is cross-report consistency, not verified independent Japanese truth. The earlier first-pass private files were **not reopened and hash-checked in this scorecard**. All original private notes remain untouched. The saved 10 Japanese candidate strings remain **private**, and no text or audio is reproduced here.

## Unresolved provenance and product-level decisions

- WX011 16-window audio source/frame mappings are historically verified *within* WX010/WX011. The **2026-10-11 Pilot-B audio-to-WX011 cross-set waveform bridge** remains `UNKNOWN`: two historical clips have exact matching core times for S11 and S15, but historical WAV/backup files were unavailable on checked hosts and the user reports no retained copy. This is **INCOMPLETE**, not a failed PCM comparison. Do not repeat broad archive searches.
- Japanese transcript accuracy `UNKNOWN`; exact acoustic boundaries `UNKNOWN`; source-wide missed-dialogue coverage `UNKNOWN`; false-dialogue error rate `UNKNOWN`; speaker DER `UNKNOWN`; final subtitle product quality `INCONCLUSIVE`.
- Evidence does not authorize choosing WhisperX/ASR thresholds, merging candidate segments into published subtitles, changing production services, or treating a technical validation PASS as product quality PASS. Ordinary subtitle operation must not depend on per-title manual checks.
- No new model inference, Demucs, audio extraction, installation, code changes, production/NAS/Jellyfin writes, publication, or private-source modifications were performed in preparing this documentary scorecard.

## Next bounded decision

This scorecard **closes the currently approved documentary aggregation step** without closing `S11-WX011` itself. Additional scientific/accuracy claims require independently supported Japanese transcription, precise acoustic references, or a separately approved evaluation method; do not infer them from stored candidate count or the three non-blind follow-ups. Under the current work authorization, only read-only verification/assessment of already frozen evidence remains available. Any production solution, threshold or pipeline design change needs its own authorization.

## Source of this scorecard

Canonical: `docs/governance/stage11/ACTIVE_WORK.md`, specifically its WX010/WX011 frozen sample, reference coverage, 2026-10-17 first-listening, 2026-11-12 source-provenance, saved-candidate, subsequent listening, and 3/3 coarse-consistency evidence checkpoints. Private records were **not** copied into Git.
