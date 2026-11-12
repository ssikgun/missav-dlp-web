# Stage11 subtitle workstream — active work

WORKSTREAM: stage11
TASK_ID: S11-BTRIAL001
STATUS: IN_PROGRESS
CONTRACT_VERSION: 1.0.0
REQUIRES_WORKSTREAMS: stage11

## OBJECTIVE

Conduct **one small, isolated, local-only feasibility experiment** for user-selected Stage11 B: on **exactly six** previously frozen WX011 clips, check whether a bounded second, **no-VAD** Whisper-type ASR request can produce hypotheses where prior WhisperX had no candidate, while separately documenting nonspeech false-text risk. The experiment measures candidate generation and source/time ownership, **not accurate Japanese recovery** or autonomous detection of all missing-dialogue intervals. Keep Qwen and other running model services unaffected. If safe compute/runtime conditions cannot be established, report `NOT_RUN / SAFE_STOP` rather than force the experiment.

## USER_APPROVAL_AND_PREDECESSOR

- On 2026-11-12, after the latest `S11-BFEAS001` read-only preflight and `SOURCE_CHAIN=PASS` user-executed output, the user agreed to the **next separately bounded isolated model trial**. This approval is for **six fixed saved local WAVs and no-VAD candidate generation only**, under the entry gates below; it does **not** authorize changing an existing GPU service, disabling Qwen, new model installation or downloads, production integration, autonomous whole-title scanning, external cloud inference, subtitle repair or publication.
- Previous `S11-BFEAS001` full active-work file is preserved **byte-identically** at [archive/S11-BFEAS001_ACTIVE_WORK_20261112.md](archive/S11-BFEAS001_ACTIVE_WORK_20261112.md). Its historical recorded result is `SOURCE_CHAIN=PASS` (WX011 pinned mapping → WX010 pinned core plan → pinned extraction manifest; same recorded source SHA) and `CROSS_STUDY_WAVEFORM_IDENTITY=UNKNOWN`. This verifies linked saved documents **within the WX010/WX011 chain only**.
- The approved Stage11 contract `1.0.0`, common contract `1.0.1`, frozen six-sample observations and B-first design memo remain unchanged. Prior `S11-DESIGN001`, `S11-RISK001`, and `S11-WX011` records remain separately archived.

## APPROVED_SCOPE

- Before any inference: read-only verify VM122 identity, current model/Whisper worker installation and actual model files/versions, real GPU RAM/RAM/disk headroom, running processes/units, and ability to test without **stopping, slowing through resource contention, restarting or modifying** operational Qwen/other services. Detect a resource conflict and **stop**; do not reserve or evict GPU memory speculatively. An observed previous 4,087 MiB GPU free is **not** an attestation of safe model loading.
- Use only existing **pinned private frozen** `S03, S11, S15` (user-reported possible spoken dialogue) and `S04, S08, S13` (user-reported no clear dialogue / nonlexical or music), each exactly once for a minimal primary pass if entry gates PASS. No new samples, scenes, titles or arbitrary media scan. Previous WX010/WX011 frozen manifest, mapping, WAV byte pins and verified `SOURCE_CHAIN=PASS` are the identity baseline; if any current source/WAV mismatch arises, **stop** rather than regenerate files. Existing human/Gemini reports are *contextual labels*, not independent Japanese transcript truth.
- A **single bounded local no-VAD ASR inference per clip** is conditionally permitted only after resource, source, engine and write-isolation gates PASS, ideally as a small CPU/offline execution if Qwen must retain current GPU resources. Reuse an already installed, actually verified audio-capable/local ASR runtime if possible. Do not quietly switch model families, add dependencies or call network-backed inference. If no suitable isolated runtime exists, `MODEL_TRIAL=NOT_RUN / SAFE_STOP` and request a new explicit choice for any dependency, GPU-memory eviction, or service changes.
- Trial sequencing: first one speech-risk clip and one non-dialogue control; halt on unexpected memory/service load, provenance failure or unsafe output. If both remain within the observed safe bounds, test up to four other fixed clips. Do not expand beyond six without new approval.
- All input/audio samples stay in the existing private VM122 directory. Store any **new, non-production outputs**, if needed, only in a fresh uniquely named, permission-restricted isolated experiment directory after ensuring it does not exist, has safe space and cannot overwrite a frozen artifact. Alternatively emit **numeric-only** results with redacted text. Limit logs and Git checkpoints to aggregate counts/hashes/status; do not place Japanese hypotheses/audio, user listening notes or identity-bearing paths in Git.
- Report separate per-case `INPUT_PIN`, `CANDIDATE_PRESENT`, `HYPOTHESIS_COUNT`, `TIME_OWNERSHIP`, `NONSPEECH_CANDIDATE_RISK`, `MODEL_RUNTIME`, `RESOURCE_IMPACT`, `ABSTAIN`, and `JAPANESE_TRUTH=UNKNOWN`. Check that existing Qwen service and any running Whisper worker remain unchanged before/after any isolated trial. Early technical candidate production does not authorize editing subtitles.
- Record one concise safe aggregate documentary result to this active work and preserve existing canonical model/worker behavior. No production or Stage12 changes.

## PROHIBITED_SCOPE

- No stopping/restarting/reconfiguring existing Qwen/Whisper or other services, GPU eviction/cache clearing, installing or downloading a model/library, changing environment variables or worker defaults, or modifying shared production runtime, scheduler, normal mode, queue or published outputs.
- No operating on more than six frozen WAV clips, no new audio extraction, source re-decode or Demucs stem creation, no changing frozen WAVs/results/manifest/source, no source-media scan or historical missing-archive search. No internet/cloud audio or transcript upload.
- No YAMNet Pilot A repeat or model threshold search to reframe the historical `13/14` nonspeech false alarms. No Gemma 3n inference by assumption; Pilot B was `MODEL_NOT_EVALUATED`.
- No audio-source/cue timestamp replacement, automatic Japanese transcript acceptance, translation via Hermes, JA-master repair, CLEAN generation or Stage12 publication. No change to external-JA/master versus whole-title translation architecture.
- No automatic candidate-free speech detector claimed by this **manually selected** six-clip trial, no linguistic accuracy or production quality PASS without independent Japanese speech/transcript reference. No sample-specific production rules or model-choice changes.
- No modifications to contracts, common governance, unrelated Downloader/Stage9 areas or their processes. Keep isolated output private and never overwrite existing files.

## ACCEPTANCE_CRITERIA

- `S11-BTRIAL001 / IN_PROGRESS` appears consistently in Stage11 router and active file on `teddy-subtitle-stage11`; previous `S11-BFEAS001` active file archived byte-identically. Contracts remain `1.0.1 / 1.0.0 APPROVED`; Project Governance CI succeeds.
- Explicit pre-inference engine/resource/source review, with reported Qwen/Whisper status and real free resources. An unknown, unavailable or conflicting runtime yields `MODEL_TRIAL=NOT_RUN / SAFE_STOP` **without** service impact.
- At most six pinned clips, balanced three possible speech and three possible non-dialogue, one local bounded no-VAD call each **only after all gates PASS**, and a two-clip safety checkpoint before remaining calls. Preserve private byte identities and no-overwrite safeguards.
- Report hypothesis **presence** vs actual correctness separately; track false-text risk on nonspeech controls, missing candidates on speech-risk cases, timing/ownership ambiguities, model/version identity, resource impact and `UNKNOWN/ABSTAIN` instead of inferring Japanese transcription quality.
- Preserve originals and all operational services/settings, no externally transferred audio, no public transcript/private content in Git, zero subtitle edits/publications, and no release or architecture decision.
- Declare `AUTOMATIC_ZERO_CUE_DISCOVERY=NOT_TESTED` and `STAGE11_PRODUCT_QUALITY=INCONCLUSIVE` regardless of hypothesis generation success; any automatic speech-trigger feature requires a separately approved design/validation path.

## EVIDENCE

- Prior fixed WX011 user listening and 6-case saved-evidence risk trial: `S03/S11/S15` potential speech omissions, `S04/S08/S13` possible nonlexical/music candidate contamination. The original user reports are speech-presence-level hypotheses; Japanese transcript truth is independently available `0/16` and exact acoustic boundaries `0/16`.
- 2026-11-12 user-executed BFEAS source-chain check printed `MAPPING=PASS`, `CORE_PLAN=PASS`, `EXTRACTION_MANIFEST=PASS`, `SOURCE_CHAIN=PASS`, `CROSS_STUDY_WAVEFORM_IDENTITY=UNKNOWN`, with `MODEL_EXECUTION=0`, `AUDIO_PROCESSING=0`, `FILE_WRITES=0`. No need to repeat identical source-chain checks absent source changes.
- Previous VM122 runtime observation (not a live current guarantee): 18,416 MiB `MemAvailable`, 10.67 GiB free disk in private analysis root; RTX 3060 12,288 MiB total / 7,825 used / 4,087 free; filtered systemd service `llama-qwen36-35b-a3b.service` active. No exact actual Whisper worker availability/loaded-model identity or local ASR runtime footprint has yet been proved.
- Historical YAMNet Pilot A `13/14` nonspeech false-positive risk and Gemma 3n Pilot B `NOT_EVALUATED` remain unchanged. Existing repo implements `process_targeted_request` as a bounded no-Silero path, but its presence does **not** attest that the local VM122 version/runtime is configured or safe to run.

## NEXT_DECISION

First perform one *read-only* VM122 installed-runtime/operational-resource/worker-route gate, with no inference. If a local no-VAD engine is verified as already installed, inputs are still pinned, and **no Qwen resource contention** is expected, run only the explicitly bounded isolated **2-clip safety canary** under this approved task, then no more than four remaining cases after checking service stability. Otherwise `MODEL_TRIAL=NOT_RUN / SAFE_STOP`, and ask the user for a concrete alternative compute option (CPU/local separate host or explicit changed resource plan). No silent stopping or replacing Qwen. No Git transcript text, no production subtitle edits, no full-film automation or Stage12 changes. The model trial cannot settle the unresolved coverage-complete JA-master vs whole-title Hermes integration design.
