# S11-MVP001 — isolated GPU int8_float16 profile candidate (2026-11-16)

STATUS: CANDIDATE_ONLY / NOT_DEPLOYED / MODEL_NOT_RUN
SOURCE_BRANCH: teddy-subtitle-stage11
CANDIDATE_BRANCH: stage11-s11-mvp001-int8-profile-candidate-20261116
SOURCE_HEAD_AT_FORK: a9817eee3b0b1137baf3bdc71ee267bac25c956e
TASK_ID: S11-MVP001
COMMON_CONTRACT: 1.0.1 APPROVED (unchanged)
STAGE11_CONTRACT: 1.0.0 APPROVED (unchanged)

## User approval and purpose

The user explicitly approved **design and isolated preparation** of a separately identified `large-v3/cuda/int8_float16` ASR route, leaving `float16` unchanged. No approval was given to load weights, start a server, install/download models, process the full title, change Qwen, write to NAS, or publish to Stage12.

The existing separate Whisper cache has a historically used CTranslate2 `large-v3` snapshot (current presence validated in a read-only check); the prior S11-BTRIAL001 six fixed WAV experiments were already completed. Do not rerun those cases or download duplicate weights. Those trials produced unverified Japanese hypotheses with nonspeech false-text risks and unreliable timestamps on several clips.

## Minimal candidate design

1. **Identity** (`teddy_discovery_asr.py`): add an exact distinct runtime tuple and profile `REMOTE_GPU_LARGE_V3_INT8_FLOAT16`. Keep the old `REMOTE_GPU_LARGE_V3` `float16` identity and local CPU identity unchanged. Never misreport int8 output as float16.
2. **GPU worker** (`teddy_discovery_asr_gpu_worker.py`): default construction remains `large-v3/cuda/float16`. The opt-in identity requires a caller-supplied absolute **local snapshot directory**, passes `local_files_only=True` to the model factory and loads lazily. The intended live launcher must separately verify snapshot containment, bytes/model provenance and startup memory gates; this candidate **does not create/start that launcher**.
3. **Protocol**: opt-in int8 requests require the exact `X-Stage11-ASR-Runtime-Profile` header. Opt-in int8 responses include a matching `runtime_profile` claim; new clients require and compare this claim, rejecting a legacy/default/mismatched response. The legacy `float16` response shape and default client behavior remain unchanged; new clients cannot safely interpret an old-server response as int8. The profile is worker-claimed execution metadata, not proof of linguistic accuracy or a cryptographic model checksum.
4. **Client** (`teddy_discovery_asr_remote.py`): default runtime identity remains `float16`; new identity must be explicitly selected by the caller and must match the response. Normal Mode/Stage11 deployment factory is **not** switched to the candidate profile automatically.
5. **Offline smoke** (`teddy_discovery_asr_int8_profile_candidate_smoke.py`): uses injected fake model/HTTP transport; checks opt-in identity, explicit local-only model arguments, default float16 factory arguments, successful matching profile, rejection of missing/wrong profile. No CUDA inference or network is required.

## Safety and remaining gates

- Keep Qwen port 8082 untouched; do not listen on 8091 or create a production systemd unit.
- Zero model loads/downloads/inference, no audio/JA/KO text exposure, no Stage12/NAS writes.
- The model/snapshot contents have **not** been re-hashed in this candidate. Offline code smoke, existing legacy smoke regressions, source-consistency and governance tests must pass **before any promotion**, and this code alone does not claim those tests ran.
- The existing Stage11 Normal Mode `HYBRID` flow requires a fresh source-bound ASR baseline plus accepted original Japanese SRT aligned to video. `DLDSS-557` has only a parser-valid 705-cue JA-labeled SRT candidate so far; Japanese linguistic truth, timing, source snapshot, title locks and complete source-bound baseline remain unverified.
- This is a **candidate design**. No change to the approved Stage11/common contracts or the production profile/worker should be inferred from its branch. Protocol negotiation, lifecycle guardrails and user consent to an actual isolated one-title model trial remain later decisions.
- When later publishing subtitles to NAS under separately approved ownership/write rules, preserve the **validated original Japanese SRT beside the corresponding video** and keep it separate from Korean output, without overwriting existing media or sidecars.

## Acceptance gates for this candidate

1. Canonical branch and selected Stage11 workstream/task remain valid; candidate changes are isolated to this branch.
2. All existing float16/default-mode behavior remains identical; only explicit int8 selection permits the new profile.
3. Response from a legacy/mismatched worker **cannot** be accepted as int8. Unknown runtime identities fail closed.
4. Offline smoke and the three existing ASR/GPU/remote smokes must run without actual CUDA/model downloads, then review diff and tests. Until they actually run, set `OFFLINE_SMOKE=NOT_RUN`; governance CI cannot substitute for the technical smoke.
5. Keep `DEPLOY=NOT_RUN`, `MODEL_RUN=0`, `NAS_WRITES=0`, `STAGE12_PUBLICATION=0` regardless of candidate code status.
