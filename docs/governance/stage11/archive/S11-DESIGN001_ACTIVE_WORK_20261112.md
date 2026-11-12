# Stage11 subtitle workstream — active work

WORKSTREAM: stage11
TASK_ID: S11-DESIGN001
STATUS: IN_PROGRESS
CONTRACT_VERSION: 1.0.0
REQUIRES_WORKSTREAMS: stage11

## OBJECTIVE

Produce a **non-operational, evidence-aware design proposal** for Stage11's automatic Korean subtitle process to address (1) genuinely spoken dialogue potentially omitted by ASR and (2) potentially non-dialogue sound represented as Japanese candidate text, while preserving Stage11/Stage12 authority, uncertainty, provenance, and unattended personal-use operation. Compare conservative approaches, identify already implemented mechanisms versus gaps, and leave architecture and product thresholds for an explicit user decision. **Design review only:** no implementation, model calls, production/runtime changes, subtitle generation, or publication.

## USER APPROVAL AND PREDECESSOR

- The user on 2026-11-12 accepted the next recommended step after the six-window risk trial: **conclude the diagnostic task and proceed to a separate design step**. This authorizes registration of `S11-DESIGN001` and read-only design/documentary work, **not** any auto-repair, filtering, feature implementation, external model connection, threshold change or deployment.
- Previous task `S11-RISK001`: six fixed WX011 cases (S03/S11/S15 and S04/S08/S13) passed *a deterministic, selected-sample technical risk-labeling trial*. Its final `ACTIVE_WORK.md` is preserved **byte-identically** at [archive/S11-RISK001_ACTIVE_WORK_20261112.md](archive/S11-RISK001_ACTIVE_WORK_20261112.md). This is an **administrative task close**, not an assertion of verified Japanese transcript accuracy, model omissions, hallucination rates or subtitle product-quality PASS.
- Earlier `S11-WX011` is still preserved separately at [archive/S11-WX011_ACTIVE_WORK_20261112.md](archive/S11-WX011_ACTIVE_WORK_20261112.md). Both the [frozen 16-window scorecard](../../discovery/STAGE11_WX011_FROZEN_16_WINDOW_SCORECARD_20261112.md) and `S11-RISK001` uncertainties remain unchanged.
- Initial read-only proposal: [STAGE11_AUTOMATED_SUBTITLE_RISK_DESIGN_20261112.md](../../discovery/STAGE11_AUTOMATED_SUBTITLE_RISK_DESIGN_20261112.md). It is **PROPOSED / NOT IMPLEMENTED**; its options do not decide the contract's unresolved Japanese-master vs whole-title-primary integration direction.

## APPROVED_SCOPE

- Read-only inspection of canonical Stage11/Stage12 source and existing records to map audio/ASR evidence, external-JA route, source-quality/targeted second evidence, Hermes translation/review, CLEAN materialization and Stage12 publication authority.
- Document separate **omission** versus **unsubstantiated candidate** risks without conflating saved candidate-segment time overlap, model hypothesis text, a user listening report, or another model's output with independent Japanese transcript truth.
- Design **alternative** non-destructive evidence and abstention flows for automatic ordinary operation, reusing existing checks. Specify which new detection evidence would be required, why source-quality on existing cues cannot detect zero-cue dialogue, and the trade-off if uncertainty remains.
- Propose an evidence-boundary/data contract, safety invariants and a proportionate *future* isolated offline validation plan. Existing six hand-picked WAVs may illustrate behavior but cannot establish general accuracy or numerical product thresholds.
- Identify questions requiring **user architecture/priority approval**, notably coverage-complete Japanese master vs whole-title-primary Korean translation and permissible auto-repair authority. Do not select a conflicting design autonomously.
- Record a safe aggregate documentary checkpoint to this file and prepare the next explicit approval decision. Keep any historical Japanese transcripts, private audio, per-person listening records and model response text out of Git.

## PROHIBITED_SCOPE

- No editing, generating, or executing Stage11/Stage12 product code, scripts, source-quality policies, model configs, GPU/worker services, queue/runtime, normal mode, stateful review or Stage12 publication behavior. No new isolated diagnostic script/run under this design-only task.
- No Whisper/WhisperX/Silero/Demucs/Gemini/Hermes inference, audio processing or re-extraction, external audio upload, or plugin/cloud inference connection.
- No VAD/ASR thresholds or product default changes; no sample-, movie-, scene- or cue-specific production rule.
- No actual Japanese-master repair, subtitle translation/generation, source replacement, artifact writes to NAS/Jellyfin, or publication; do not change downloader/Stage9/other workstreams.
- Do not invent independent transcript labels, precise acoustic boundaries, speaker error rates, omission/false-positive rates or product-quality PASS based on six selected examples or model-model agreement.
- Preserve frozen data, source hashes, existing first-pass review records and archived predecessor task states. No private Japanese strings or audio in Git.
- Do not resolve the approved design conflict between Japanese coverage-complete master and whole-title primary translation without user choice. Any later implementation, isolated model test, architecture commitment, deployment or publication requires separately scoped user authorization.

## ACCEPTANCE_CRITERIA

- Canonical `teddy-subtitle-stage11` router and this active file both show `S11-DESIGN001 / IN_PROGRESS`, common contract `1.0.1` and Stage11 design contract `1.0.0 / APPROVED` remain unchanged. The predecessor `S11-RISK001` file is archived at exact original blob SHA.
- Design document distinguishes verified implementation facts, *proposals*, recorded six-window risk observations, and `UNKNOWN / INCONCLUSIVE` quality conclusions.
- Candidate architecture covers both missing-dialogue discovery with **no ASR source cue** and conservative handling of **context-overlapping / potentially non-dialogue** hypotheses. It does not treat a risk flag as publication/repair approval.
- Source/cue/time/provenance ownership remains deterministic, semantic text belongs to Hermes within its contract, and the Stage12 no-overwrite publication boundary remains unchanged.
- Document more than one viable approach, risks of false exclusion and false insertion, and explicitly identify any user decision that blocks choosing a concrete product path.
- Supply a bounded future verification approach with clear abstentions but no invented thresholds or pretext that six selected samples represent full production accuracy.
- Zero runtime/model/source/translation/product/publication changes; historical `S11-RISK001` technical PASS does **not** become Stage11 product PASS.

## EVIDENCE

- Preceding **six-case deterministic diagnostic** was reported user-executed on VM122: 3/6 `POTENTIAL_MISSED_DIALOGUE` and 3/6 `POTENTIAL_NON_DIALOGUE_CANDIDATE` in risk-selected frozen samples; `DIAGNOSTIC_ACCURACY=NOT_ESTABLISHED`, `JAPANESE_TRANSCRIPT_TRUTH=UNKNOWN`, `SOURCE_CORE_INPUT_RECHECK=NOT_PERFORMED`, `PRODUCT_QUALITY=INCONCLUSIVE`. No model inference/file writes in that trial.
- Frozen WX011 16-window independent references remain Japanese truth `0/16`, speech-presence `10/16` (7 speech, 3 non-dialogue), speaker count `2/16`, exact speech boundaries `0/16`. User/Gemini agreement is supportive hypothesis evidence, not an independent Japanese reference.
- Canonical source inspections: `teddy_discovery_asr_gpu_worker.py` has Silero-based `process_request` and no-VAD `process_targeted_request`; `teddy_discovery_asr_source_quality.py` examines surviving cue texts and can emit `REQUIRE_SECOND_EVIDENCE`; `teddy_discovery_targeted_second_evidence.py` constructs existing-cue-based plans; `teddy_discovery_stage11_normal_mode.py` marks supplementary candidates `DISABLED_UNVERIFIED_ACCURACY` and requires accepted external JA for its HYBRID route. These are repository-code facts, **not** a VM122 deployed-revision attestation or a recovery-quality demonstration.
- The approved Stage11 contract's two possible integration directions remain unresolved and user-owned: coverage-complete JA master versus whole-title primary translation. No architecture or product acceptance thresholds were approved by this task transition.

- 2026-11-12 **user clarification / B-first design prioritization**: The user confirmed the core product improvement goal is **B — automatically recover candidates for potentially missed spoken dialogue by obtaining bounded additional audio evidence**, rather than ending with observation-only A. In this **design-only** task A is an audit/abstention support within B, while C's actual validated Japanese/KO output integration remains future and separately approved. The canonical memo has been expanded to show that today's cue-based source-quality and targeted-second-evidence planner **cannot nominate a zero-cue interval**; discovering such an interval needs a separate source-bound signal, which itself may have false alarms and must not be conflated with transcript truth. Proposed future reuse of no-Silero targeted worker is conditional on separate explicit permission, provenance, resource bounds and credibility checks. No numerical policy thresholds, architecture, model execution, WAV modification, code/service/config edits, subtitles, NAS/Jellyfin writes or publication. Japanese transcript truth remains `0/16`, precise boundaries `0/16`, final Stage11 quality `INCONCLUSIVE`; original six-risk-sample trial is not rerun.

- 2026-11-12 **B feasibility documentation precheck** after user approval to prepare a small trial scope/success criteria: Reviewed **existing** Pilot A, Pilot B and core STT records plus canonical ASR response schema, without rerunning any pilot or model. Pilot A's fixed YAMNet frame rule showed 13/13 speech-containing context clips nominated **but 13/14 non-dialogue clips falsely nominated**; historical trigger acceptance **FAIL**, so YAMNet alone is **not an approved Japanese-dialogue trigger**. Pilot B Gemma 3n was `BLOCKED_SAFE_STOP / MODEL_NOT_EVALUATED`; its audio inference never ran. Earlier core STT output coverage (Whisper 13/13, Reazon 11/13) did not establish correct Japanese recoveries (confirmed 0/13). Current worker's response records `vad_region_count` rather than VAD **start/end regions**, and cue-based targeted planning still cannot nominate zero-cue speech. A bounded six-case future test is **PROPOSAL_ONLY / NOT_RUN**; original source-core bridge and any same-source independent acoustic records are `VERIFY_REQUIRED`. Details and conservative technical-vs-product acceptance criteria were added to the [design memo](../../discovery/STAGE11_AUTOMATED_SUBTITLE_RISK_DESIGN_20261112.md) section 4b. No product-code, model, audio, service, threshold, subtitle, NAS/Jellyfin or external writes.

## NEXT_DECISION

The user-confirmed **B-first direction** is preserved. The prior YAMNet Pilot A **failed** as a reliable sole dialogue trigger (13/14 historical non-dialogue false nominations); Gemma 3n Pilot B ran **no inference**. The current worker exposes a VAD **region count, not independently usable region intervals**; direct zero-cue speech detection is therefore **not proven** by these saved facts. The [B feasibility precheck in design memo §4b](../../discovery/STAGE11_AUTOMATED_SUBTITLE_RISK_DESIGN_20261112.md) specifies a **not-yet-executed**, small source-verified trial, abstentions and safety/resource gates. First choose a credible, source-bound speech-supporting trigger and verify any saved acoustic metadata; then **seek a new explicitly approved Stage11 task** for even a small model/audio execution. No model call, audio extraction/processing, trial runtime, threshold, production code or subtitle publishing is authorized under `S11-DESIGN001 / IN_PROGRESS`. Original independent Japanese references remain 0/16; final product quality `INCONCLUSIVE`. Avoid repeating previous six-case risk check, YAMNet Pilot A, or historical missing-audio searches. The Stage11 Japanese master vs whole-title-primary integration decision remains user-owned.
