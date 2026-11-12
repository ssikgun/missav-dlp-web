# Stage11 subtitle workstream — active work

WORKSTREAM: stage11
TASK_ID: S11-BFEAS001
STATUS: IN_PROGRESS
CONTRACT_VERSION: 1.0.0
REQUIRES_WORKSTREAMS: stage11

## OBJECTIVE

Perform a **small, read-only, source-bound preflight** for the user-selected Stage11 B path (independent nomination of potentially missing spoken dialogue followed by bounded second audio evidence). Establish whether the six frozen S11-WX011 probe samples are suitable for a future isolated no-VAD feasibility experiment, and whether current VM122 environment/resource and preserved source identities satisfy a safe entry gate. **This task does not authorize a model inference or audio experiment**, implement a detector, decide thresholds, or modify any subtitle.

## USER_APPROVAL_AND_PREDECESSOR

- On 2026-11-12 the user accepted the proposed next work after the WX010/WX011 stored-evidence inventory: register **`S11-BFEAS001`** and first inspect VM122 runtime capacity and original-audio provenance **read-only**, with any actual no-VAD inference requiring **separate explicit approval** after verifying conditions.
- The predecessor design task `S11-DESIGN001` remains preserved **byte-identically** at [archive/S11-DESIGN001_ACTIVE_WORK_20261112.md](archive/S11-DESIGN001_ACTIVE_WORK_20261112.md). Its B-first design memorandum [STAGE11_AUTOMATED_SUBTITLE_RISK_DESIGN_20261112.md](../../discovery/STAGE11_AUTOMATED_SUBTITLE_RISK_DESIGN_20261112.md) remains a **proposal, not implemented code or product-quality proof**.
- The earlier `S11-RISK001` risk trial and `S11-WX011` frozen-listening work remain independently archived with their original observations and denominators; **do not repeat the same fixed deterministic 6-case diagnostic**.

## APPROVED_SCOPE

- Read-only confirm actual VM122 host identity, available CPU/RAM/GPU/disk capacity, relevant running model/worker service status, and observed live configuration **without restarting, stopping, modifying, or probing with inference**. Do not assert a source checkout or deployment SHA without verifying it.
- Read-only inspect a **small, explicitly bounded subset** of the already frozen six WAVs `S03/S11/S15/S04/S08/S13`, their historical pinned identity/manifest/mapping records, and the original WX010 source/core identity relationships. Check hashes, source ownership/time mapping and presence of any *existing*, hash-bound independent acoustic/VAD region evidence without re-extracting or processing audio.
- Do not search for the historically unavailable Pilot-B audio tarball or re-open arbitrary unrelated folders. If source hash bridging to a different past study is impossible, report `SOURCE_BRIDGE=UNKNOWN`; exact matching clock times are not matching PCM.
- Separate `METADATA_PRESENT`, `HASH_IDENTIFIED`, `SOURCE_BRIDGE_VERIFIED`, `SPEECH_CANDIDATE_OBSERVED`, and `JAPANESE_TRANSCRIPT_TRUTH` as distinct claims; absence of ASR cue does not mean silence, and an existing acoustic event classification does not prove Japanese dialogue.
- Produce one **short read-only preflight result and bounded next authorization proposal** covering six selected cases and historical non-dialogue controls, reusing already archived failures rather than re-running YAMNet. Preserve `UNKNOWN / INCONCLUSIVE` quality labels.
- Record only aggregate non-private checkpoints under this task; never include Japanese transcript strings, private WAV content, source paths that reveal personal titles, or listening notes in public Git.

## PROHIBITED_SCOPE

- **No** Whisper/WhisperX/Silero/Demucs/YAMNet/Reazon/Gemma/Hermes/Gemini model execution, no-VAD re-inference, audio decoding, resampling, re-extraction, transcription, or external audio upload **in this task**.
- No runtime/service/container changes, process termination, package/model download/install, GPU resource reconfiguration, thresholds, worker queue, normal mode, production code, or trial scripts executed on VM122.
- No WAV/manifest/historical result file writes or overwrite; no scans of unrelated private media; no resurrection search for missing Pilot-B archives. No new sample/title/cue-specific production heuristic.
- No altering Japanese source/master, Hermes semantic/translation route, Stage11 CLEAN materialization, Stage12 publishing, subtitle release, NAS/Jellyfin or unrelated Downloader/Stage9 workstreams.
- No performance or product-quality PASS based on six selected examples, model hypothesis agreement, mere file existence, or absence of metadata in a small scan. No architecture conflict resolution or threshold selection without explicit user approval.
- Do not relax the governance checker or modify common/Stage11 contracts.

## ACCEPTANCE_CRITERIA

- Canonical branch `teddy-subtitle-stage11` router and Stage11 active file both show `S11-BFEAS001 / IN_PROGRESS`; versions `1.0.1 / 1.0.0` contracts unchanged; `S11-DESIGN001` history archived byte-identically.
- VM122 preflight (when user-supplied read-only command has actually run) reports real running resource conditions and exact scope: source identity/path/security checks, available RAM/GPU/disk and relevant service states; missing access or mismatched identities are `VERIFY_REQUIRED`, not automatic PASS.
- Clear accounting of what has **already** been checked (six sample WAV/JSON pins, 16 sampled JSONs without VAD interval fields, bounded extra 14-directory inventory with 4 large text files skipped) versus what is newly verified; no redundant model runs or archive hunts.
- A credible independent speech-supporting trigger for **zero-cue intervals** is either found with trustworthy source ownership or explicitly remains `TRIGGER_NOT_VALIDATED`; mere YAMNet Speech from its historical failed rule or ASR text alone is not adequate.
- If a later isolated inference is proposed, describe an explicitly bounded six-window plan, realistic resource/provenance preconditions, non-dialogue controls, no-overwrite safeguards, ambiguous/unsupported evidence treatment and technical-vs-Japanese-product acceptance separately. **Do not execute it under this task.**
- No audio/model, production/worker/service/config or subtitle/NAS/Jellyfin writes; outcome `PRODUCT_QUALITY=INCONCLUSIVE` and independent Japanese transcript truth `UNKNOWN`.

## EVIDENCE

- Latest preceding `S11-DESIGN001` summary: user selected **B** as goal, A as supporting risk record and C as later source-to-subtitle integration. Its design record is linked above. Japanese master versus whole-title Hermes primary integration remains a user-owned unresolved design decision.
- Earlier VM122 user-executed six-window pin check: sample WAV SHA/time and 32 stored WX010 JSON file identities PASS; saved-evidence diagnostic found only *risk labels*, 3 potential omissions and 3 potential unsupported candidates. No independent Japanese reference (0/16 in WX011), exact speech timing (0/16), or demonstrated automatic recovery.
- 2026-11-12 user-executed bounded saved-metadata check: in the S11/S15/S04 candidate-core JSON references, **16 distinct pinned files** were inspected and no selected `vad_regions`/`speech_regions`/`vad_timestamps`/`speech_timestamps`/`vad_region_count` fields were found. This does not establish their absence elsewhere.
- 2026-11-12 user-executed bounded filename/key scan: 14 directories, 26 files, 12 small text files content-inspected, **4 oversized text files skipped**, no matching VAD region key files within scan, 8 files with literal source-media SHA. The user's reported output declared `SCAN_COMPLETE=True`; this only means the configured directory-entry caps were not hit, not a full private-disk/source or speech-accuracy audit. SHA string presence is not a matching waveform attestation.
- Historical YAMNet Pilot A flagged **13/13** speech-containing context clips but **13/14** non-dialogue clips (historical trigger acceptance FAIL), so YAMNet alone is not a reliable Japanese speech selector. Historical Gemma 3n Pilot B conducted **zero** audio inference and was `MODEL_NOT_EVALUATED`; no upgrade or substitute is assumed.
- The canonical GPU worker offers Silero-based `process_request` and bounded no-Silero `process_targeted_request`, but standard output includes only `vad_region_count` and segment hypotheses, not raw VAD region bounds; the current cue-based targeted planner cannot nominate zero-cue audio intervals.

- 2026-11-12 **user-executed VM122 read-only resource/source-document preflight**: `HOST=PASS` on `local-llm`; `/proc/meminfo` `MemAvailable=18,416 MiB`, disk free under private analysis root `10.67 GiB`; RTX 3060 nvidia-smi total/used/free `12,288/7,825/4,087 MiB`; filtered systemd listing found **one** matching service, `llama-qwen36-35b-a3b.service loaded active running`. This narrow listing does **not** prove the Whisper worker is absent, that Qwen is the actual served model, or that 4,087 MiB can safely accommodate a targeted inference. Five source records parsed read-only: frozen WX011 manifest and blind mapping had exact expected SHA pins (`PASS`); `source-identity.json`, `audio-extraction-manifest.json`, `core-plan.json` were opened **without independently asserting exact-file hashes** (`PIN=NOT_PREPINNED`). The literal source-media SHA appears in all five inspected files but **does not establish matching audio waveform**. Six blind/sample mappings passed. User output: `RUNTIME_RESOURCE_PREFLIGHT=COMPLETE`, `CROSS_STUDY_WAVEFORM_IDENTITY=NOT_ESTABLISHED`, `MODEL_EXECUTION=0`, `AUDIO_PROCESSING=0`, `FILE_WRITES=0`. Result is **READ_ONLY_PREFLIGHT=PARTIAL_PASS / MODEL_TRIAL_READY=VERIFY_REQUIRED**. Do not infer production deployment revision, independent speech-region trigger or Japanese accuracy from this inspection. Previously validated WX011 WAV and WX010 JSON identities need not be redundantly rechecked.

## NEXT_DECISION

The actual read-only VM122 resource/status inventory is now **COMPLETE** (18,416 MiB available RAM, 4,087 MiB GPU free, 10.67 GiB disk free at observation time, with filtered `llama-qwen36-35b-a3b.service` active). This is **not** authorization or guaranteed headroom for simultaneous inference. The minimal remaining entry gate is **one source-chain-only read-only SHA check**: the **already pinned** WX011 private blind mapping's `core_plan_sha256` and `audio_extraction_manifest_sha256` must match the corresponding existing WX010 files; map their declared source SHA and extraction core-plan hash without reopening WAV/JSON candidate outputs. `source-identity.json` remains unpinned without an authoritative expected hash; cross-study waveform identity stays `UNKNOWN`. If the chain cannot be established, report `SOURCE_CHAIN=VERIFY_REQUIRED`, no inference. Even with `SOURCE_CHAIN=PASS`, reliable candidate-free Japanese speech nomination remains `TRIGGER_NOT_VALIDATED` and the user's separately approved inference task is required for any subsequent bounded no-VAD test. Preserve `S11-BFEAS001 / IN_PROGRESS`, quality `INCONCLUSIVE`, and no worker/model/audio/product/runtime changes. Do not rerun the 6-case deterministic risk labels or Pilot A, search lost Pilot-B archive, or assume current 4,087 MiB GPU free is enough.
