# Stage11 subtitle workstream — active work

WORKSTREAM: stage11
TASK_ID: S11-RISK001
STATUS: IN_PROGRESS
CONTRACT_VERSION: 1.0.0
REQUIRES_WORKSTREAMS: stage11

## OBJECTIVE

Evaluate, **in an isolated offline diagnostic only**, whether existing frozen evidence can flag (A) suspected missed spoken dialogue and (B) suspected non-dialogue candidate contamination without claiming Japanese transcript accuracy or changing the automatic subtitle product. Use only the six previously frozen WX011 sample windows S03/S11/S15 and S04/S08/S13 and the previously saved WX010 outputs. Favor reuse of the current ASR source-quality and targeted-evidence infrastructure. This task is a **risk-diagnostic prototype**, not authority to enable recovery, filtering, or publication.

## USER APPROVAL AND PREDECESSOR

- The user explicitly approved the proposed `S11-RISK001` registration and bounded isolated six-sample risk evaluation on **2026-11-12**. No model inference, live service work, production implementation or subtitle deployment is implied by that approval.
- Predecessor `S11-WX011`: its approved frozen-evidence and documentary scorecard phase is recorded; historical original ACTIVE_WORK is preserved byte-for-byte at [archive/S11-WX011_ACTIVE_WORK_20261112.md](archive/S11-WX011_ACTIVE_WORK_20261112.md). Transitioning away from that task is **administrative succession**, **not** a product-quality PASS or a claim that all scientific accuracy questions were resolved.
- Frozen source scorecard: [docs/discovery/STAGE11_WX011_FROZEN_16_WINDOW_SCORECARD_20261112.md](../../discovery/STAGE11_WX011_FROZEN_16_WINDOW_SCORECARD_20261112.md). Its `UNKNOWN`, `INCONCLUSIVE`, `UNRESOLVED` and reference-denominator limitations remain binding.

## APPROVED_SCOPE

- Read-only verification of the six frozen sample IDs, existing private WAV/hash/time mappings and pre-existing WX010 WhisperX condition/core JSON outputs; preserve the frozen 16-window manifest and all first-pass observations.
- Read-only review of current Stage11 source-quality, Silero VAD, targeted no-VAD ASR interfaces, targeted second-evidence policy, Normal Mode and Stage12 output boundaries. Identify which protections already exist versus gaps; repository source review does not prove the live VM122 installed revision.
- Design and, only in an **isolated non-production scratch/worktree**, make a small deterministic diagnostic prototype **using pre-existing saved evidence**, not new ASR inference. It may label evidence as `POTENTIAL_MISSED_DIALOGUE`, `POTENTIAL_NON_DIALOGUE_CANDIDATE`, or `INCONCLUSIVE`, with provenance, short-window intersection context, and explicit missing-reference notes. These are **risk indicators**, not final subtitle decisions.
- Validate the prototype with the same exact six frozen cases: S03/S11/S15 for candidate-free/late-speech omission risk and S04/S08/S13 for context-spanning/non-dialogue candidate risk. Use minimal proportionate offline checks; no score thresholds or condition changes.
- Report what the existing evidence actually supports, the unresolved Japanese transcript/boundary/DER dimensions, cases where simple heuristics would misclassify audio, and whether a later **separately authorized** product change is worth considering. Do not extrapolate sample-specific findings to a population accuracy rate.
- A concise safe aggregate documentation checkpoint may be recorded in this Stage11 ACTIVE_WORK. Keep private Japanese hypotheses/audio/individual listening records outside Git.

## PROHIBITED_SCOPE

- **No new model inference** (Whisper, WhisperX, Silero, targeted/no-VAD, Demucs, Gemini, Hermes or other model); no audio re-extraction, new audio processing, model installation/replacement or inference through existing running services.
- No changes to production Stage11/Stage12 code, normal-mode runtime, worker services, systemd, GPU configuration, model caches, Docker, downloader/Stage9, NAS/Jellyfin or production databases.
- No accepted translation, subtitle generation, SRT rewriting, publishing/replacing existing output or Stage12 boundary changes.
- No VAD thresholds/defaults, ASR route/quality filters, global policy, new background automation, or sample/title-specific production exceptions.
- No new selections or changes to the frozen 16 samples; no modification/overwriting of WX010/WX011 original data, previous first-pass user reports, or the archived `S11-WX011` work record.
- No external audio upload/sharing, new third-party calls, private Japanese transcript strings or audio in Git. Prior user-supplied Gemini output is an external **hypothesis**, not ground truth.
- Do not resolve the contract's coverage-complete JA vs whole-title translation design priority; user approval is required for any conflicting implementation choice.
- Incomplete provenance, missing references or ambiguous classifications remain `UNKNOWN/INCONCLUSIVE`; never report a production-ready or semantic-quality PASS from technical diagnostic results.

## ACCEPTANCE_CRITERIA

1. Remote canonical branch `teddy-subtitle-stage11` has matching Stage11 router and this active-work record: `S11-RISK001 / IN_PROGRESS`; contract `1.0.0` and common `1.0.1` remain approved and unchanged. `S11-WX011` full historical text is retained at the archive path and verified.
2. Source and sample identity/hash/time references for all **six** already frozen evaluation windows are verified from existing evidence or clearly marked **VERIFY_REQUIRED**. Zero expansion to other windows or unsupported input copies.
3. Diagnostic separates **missing-dialogue risk** from **spurious-candidate risk**, differentiates overlapping long-context candidate spans from spoken words **inside** short WAVs, and emits traceable abstentions rather than invented Japanese dialogue.
4. Any isolated offline prototype is reproducible, bounded to the saved six evidence cases, and shows its expected failure/uncertainty behavior without making real service/model calls.
5. The original 16-window independent-reference counts remain fixed: Japanese transcript truth **0/16**, speech-presence references **10/16** (7 speech/3 non-dialogue), speaker-count **2/16**, exact acoustic boundary **0/16**. Follow-up human/Gemini agreement must not be promoted to reference truth.
6. No production/code/service/output writes, models, extraction/Demucs, private evidence replacement, external uploads, NAS/Jellyfin activity or subtitle publication. Documentation-only registration commits are permitted.
7. Produce a brief PASS/INCONCLUSIVE/VERIFY_REQUIRED diagnostic report and leave any product implementation, threshold adjustment or live model trial for a new explicit approval and workstream authorization.

## EVIDENCE

- Registered from user approval on 2026-11-12 after the prior workstream's frozen 16-window scorecard and user/Gemini six-window risk analysis.
- Historical frozen manifest SHA-256: `3b4ac21598d3a8f7e01588a760a0b6f88644d3100519705f789641616abbf478`; blind audio provenance SHA-256 `c28a02c0f8615d61cb73bd525e3d5469fd87725e0148a624389a1ca511aa97f7`. Pins are historical reference values, **not** proof that every private file was rechecked during registration.
- Existing canonical code exhibits Silero-based `process_request`, targeted no-Silero `process_targeted_request`, ASR source-quality decisions `KEEP/OMIT/REQUIRE_SECOND_EVIDENCE`, and Normal Mode `supplemental_status=DISABLED_UNVERIFIED_ACCURACY`. These are code-path facts, not verified fixes to omission or candidate hallucination.
- No independently verified Japanese text reference exists in the frozen 16 windows, no trustworthy error rate is measured, and product quality is `INCONCLUSIVE`.

## NEXT_DECISION

First perform a read-only six-case and existing-code preflight under `S11-RISK001`; then draft the minimal isolated **saved-evidence-only** diagnostic checks and demonstrate what risk each can and cannot identify. Do not run any ASR/VAD/model, alter original evidence or release software. If verification uncovers missing trusted inputs, report `VERIFY_REQUIRED` rather than guessing or extending scope. Product action remains a **separate future approval decision**.
