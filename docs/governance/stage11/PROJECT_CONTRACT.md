# Stage11 subtitle design contract

CONTRACT_VERSION: 1.0.0
PROJECT_CONTRACT_STATUS: APPROVED
APPLIES_TO: Stage11 subtitle acquisition/generation and its Stage12 publication boundary only

This is the approved Stage11-specific contract. It applies to subtitle work even when the implementation files are in the repository root. It does not apply to unrelated Discovery, UI, or Downloader operations. Approval preserves the design goals and safety policies; it does not authorize a Stage11 implementation task.

## Stage11 subtitle product goals — APPROVED_GOAL

The final product goal is a safe, traceable, automatically generated Korean subtitle that does not depend on per-title manual subtitle review during ordinary operation:

1. Produce natural, easy-to-understand Korean dialogue.
2. Combine trusted external Japanese subtitles with real audio and ASR evidence where each source helps; neither source is blindly treated as ground truth.
3. Recover real spoken dialogue missing from an external Japanese subtitle when supported by evidence.
4. Prevent sentence breaks, duplicate meaning, and semantic spill across neighboring cues.
5. Compose subtitles around real utterance and sentence boundaries.
6. Separate speakers and format line breaks when evidence supports it.
7. Conservatively detect omissions, hallucinations, mistranslations, and context shifts.
8. Automate ordinary operation without relying on a user's manual subtitle review for every title.
9. Preserve traceability among source material, evidence, decisions, and generated output.
10. Send only validated subtitles through Stage12's safe publication boundary.

These are goals, not claims that the current product meets them. Unagreed numerical thresholds remain unresolved; do not invent them.

## Stage11 role and safety policies — FROZEN_POLICY

| Owner | Authority |
| --- | --- |
| Deterministic code | Stable identity and source indexes, accepted timestamps, structural/evidence validation, materialization, and publication. |
| Whisper/ASR | Audio and speech evidence. ASR output is a hypothesis, not ground truth. |
| Hermes | Evidence-based semantic interpretation, Korean translation, and justified source-text repair/recovery. It does not own cue identity/order, timestamps, routing, or publication. |
| External Japanese | Trusted text evidence when validated; it does not automatically define complete speech coverage. |

- Preserve uncertainty. Do not invent dialogue to fill a gap; do not omit uncertain dialogue merely to make output cleaner. Unsupported or conflicting decisions remain conservative.
- Never use external Korean subtitles as translation truth.
- Keep existing Stage12 ownership, collision protection, and no-overwrite behavior. A candidate or private artifact is not authorization to publish or replace an existing subtitle.
- Keep Stage9 completion behavior independent from subtitle failure.
- Do not add title-, DVD-, cue-, phrase-, or sample-specific production exceptions or silently weaken validation limits.
- Model execution, ASR, service/queue changes, deployment, NAS/Jellyfin writes, and publication require explicit authorization in the Stage11 active task.

## Design record and conflict handling

### APPROVED_GOAL: coverage-complete Japanese evidence

The 2026-10-02 handoff records this future direction:

`external JA + automatic ASR evidence -> repaired/coverage-complete JA master -> Hermes -> Korean`

The Japanese master is a future product/design goal for joining useful external-JA evidence with supported speech missing from it. The canonical source does not establish this as a completed normal-mode feature.

### PROPOSED_DESIGN: whole-title primary translation

The 2026-10-07 direction reset prefers a whole-title Hermes primary translation when stable, with bounded partitioning as fallback. Boundary, speaker, and semantic-ownership rules belong in the primary translation; the handoff rejects broad temporal re-review as the production solution because it caused semantic drift in the cited experiment.

This implementation direction does not erase the coverage-complete Japanese-master goal or authorize an AI session to decide how the two directions are combined. If priorities or architecture conflict, leave the conflict open and ask the user to choose before dependent work.

### IMPLEMENTED and candidate-only evidence

- The canonical Stage11 source branch contains an external-JA/ASR evidence route, accepted affine timing, a Hermes whole-title path with the existing bounded fallback, and deterministic review/materialization and Stage12 validation boundaries.
- The 2026-10-12 Normal Mode record documents two actual native translations and mechanical source/output protections. It does not claim full backlog completion, complete dialogue recovery, or perfect recognition.
- The 2026-10-13 P2-L candidate defines group-wide REPAIR authority for an absorption group only with a separately validated request/result, membership/owner, provenance, and execution evidence. This candidate contract is not by itself permission to generate or publish output.
- P2-N (2026-10-14) reports that an isolated CLEAN artifact, produced from a P2-M9 candidate, passed Stage11 completion and read-only Stage12 artifact preflight. This is a technical validation result for that private artifact.

## UNRESOLVED product quality

- P2-O (2026-10-14) reports `NEEDS_HUMAN_REVIEW`: 15 long gaps were `COVERAGE_GAP_SUSPECTED`, three were `UNVERIFIED`, sampled text changes could be context-shifted, and speaker identity was not represented in the compared SRT evidence. These are not confirmed omissions and do not prove improved semantic quality.
- Complete automatic recovery of missing dialogue, natural cue/sentence boundaries, speaker separation, line-break quality, and final product quality have not passed their required evidence review.
- P2-N's isolated structural PASS and P2-O's structural comparison do not establish subtitle product-quality PASS or authorize replacement/publication.
- No numerical acceptance thresholds for remaining semantic-quality goals are approved. Keep them `UNRESOLVED` until the user approves evidence and criteria.
- The priority and integration between the coverage-complete Japanese-master goal and the whole-title primary-translation direction remain a user decision if they conflict in implementation.

## Workstream state

The Stage11 design contract remains APPROVED independently of the current
workstream task state. The current TASK_ID and STATUS are authoritative in
`docs/governance/stage11/ACTIVE_WORK.md` and must match the Stage11 entry in
`docs/governance/ACTIVE_WORK.md`. INACTIVE with TASK_ID NONE means no Stage11
task is currently authorized and leaves the approved design contract in force.
BLOCKED identifies a registered task whose execution is blocked while the
approved contract remains in force. Any mismatch between the Stage11 active-work
record and router must fail closed. A Stage11 state applies only to Stage11 and
does not pause an independent workstream.
