# Stage11 subtitle design contract

CONTRACT_VERSION: 2.2.0
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
| External Japanese | Optional validated comparison evidence; neither semantic accuracy nor complete speech coverage is presumed. |

- Preserve uncertainty. Do not invent dialogue to fill a gap; do not omit uncertain dialogue merely to make output cleaner. Unsupported or conflicting decisions remain conservative.
- Never use external Korean subtitles as translation truth.
- Keep existing Stage12 ownership, collision protection, and no-overwrite behavior. A candidate or private artifact is not authorization to publish or replace an existing subtitle.
- Keep Stage9 completion behavior independent from subtitle failure.
- Do not add title-, DVD-, cue-, phrase-, or sample-specific production exceptions or silently weaken validation limits.
- Model execution, ASR, service/queue changes, deployment, NAS/Jellyfin writes, and publication require explicit authorization in the Stage11 active task.

## Approved architecture — ASR-FIRST HYBRID V2 (2026-11-22)

User explicitly approved the design and reuse plan recorded in f40d39a680fbd85139012428fce9631ed9c1ae4f. V2 supersedes the external-JA-centered architecture and places evidence-supported JA master before primary translation. Original product goals, role boundaries and data protections remain. Design approval does not authorize production changes or model execution.

### Approved fixed topology and boundaries
1. Preserve Stage9 independence, source identity, original audio, optional validated external JA acquisition and original bytes. External availability/failed alignment is not itself a generation blocker; explicit evidence mode retained.
2. Reuse source-bound full-title local Whisper large-v3 and cached baseline. ASR is a candidate timeline/evidence set, not ground truth. Preserve word timings and available confidence/VAD evidence; raw confidence availability/schema requires inspection, not assumptions.
3. Align usable external JA to the video timeline with existing affine implementation, compare both sources symmetrically including ASR-only and external-only candidates and disagreements. Do not overwrite one source wholesale, blindly union transcripts, or count agreement of correlated STT as proof. No accepted external JA -> explicit ASR-first path with equal quality safeguards. This approved V2 policy supersedes the legacy Normal Mode accepted-HYBRID requirement in the target architecture; legacy execution remains unchanged until validated migration.
4. Hermes identifies semantic discrepancies and evidence-supported decisions; deterministic code owns identity, accepted source-supported timing, provenance, structural validation. Selectively recheck suspected windows using existing targeted ASR, including gaps detected from audio evidence independent of existing cue list. Demucs only as optional additional evidence for suitable noisy windows, not default replacement or a new mandatory full-title stage. Reuse WX007/WX010/WX011 artifacts if available: historical comparisons inconclusive for transcript accuracy; no automatic adoption of WhisperX, new model or blanket preprocessing.
5. Preserve independently supported speaker turns and sentence boundaries before primary translation. Existing pyannote CPU feasibility only; global speaker consistency, turn accuracy and within-cue utility unproven. Do not guess identities/sex/relationships; unknown/overlap retained, no forced splitting.
6. Materialize source-bound JA master with explicit accepted, rejected and uncertain candidate decisions, stable cue/source identities and timestamps; retain original external JA and raw ASR separately. Preserve plausible dialogue conservatively, no promotion of unsupported synthetic speech. Material unresolved evidence must not silently be called quality PASS; approved bounded fallback or title-level hold, no mandatory manual per-title action. Policy/acceptance specifics need user decision; no flip of AUTO_INSERT alone.
7. Reuse whole-title Hermes primary translation if feasible, existing context-preserving partition fallback, dynamic profile, native runner, stage-local receipt reuse. Input is JA master, not a new fixed-64 translation architecture. Reuse targeted review and CLEAN materializer with necessary schema/ownership adaptations. No blanket rewriting, forced casual speech, or LLM ownership of timestamps.
8. Reuse existing Stage12 validator, no-overwrite publication, title isolation/locks, queue, timer, NAS/Jellyfin path. Keep original external JA, self-generated JA master and final KO distinct (local comparison and NAS original-sidecar requirement preserved, naming/location/lifecycle decision outstanding). Resolve current Git metadata issue before activation. Stage9 unaffected.

### Approved opt-in CT108 SIWC primary-translation backend — 2026-11-27 (v2.1.0)

User explicitly approved adding an independent CT108 Sign in with ChatGPT (SIWC) direct Responses API backend as an opt-in alternative for primary Japanese-to-Korean translation only, and isolated source development/offline validation. This narrow amendment qualifies the Hermes primary-translation references in the role table and topology item 7 above: the explicitly selected SIWC adapter may perform primary Korean translation under the same semantic-authority and deterministic validation boundaries. Hermes remains the existing/default execution route and retains semantic adjudication, source repair/recovery, targeted review and final review in this phase. No change to ASR-FIRST HYBRID V2 ordering, identity/timing authority, source evidence, uncertainty, provenance, partition/resume, quality or Stage12 publication policies.

- Reuse the verified independent SIWC authentication module and official direct Responses route, with secure isolated profiles, automatic refresh capability, no Codex/Hermes token reuse, private endpoints, credential disclosure, paid API fallback or automatic backend switching.
- Preserve existing CT120 default and configuration, CT121 opt-in implementation and stopped state, and V2-E execution hold. Direct adapter is explicitly selected, not an implicit replacement or failover. Support validated model and reasoning configuration, pinned and traceable per invocation/title with existing receipt/reuse policy preserved. GPT-6-Luna medium is a candidate for ordinary translation, not a production setting or a mandate to reduce review reasoning.
- Reuse existing whole-title primary translation, context-preserving partition fallback, strict result validation and source/prompt/backend-bound receipt/resume mechanisms. Do not weaken checks or mix incompatible unfinished artifacts. Determine exact integration boundaries from source; if the existing interface cannot isolate primary translation from semantic/review requests, report the conflict rather than reroute those requests.
- This amendment authorizes design only; the active task records the isolated implementation scope. No additional live model inference, real media/subtitle transmission, account/production/service/queue/DB/NAS/Jellyfin changes, deployment or publication without separate explicit approval.

### Approved isolated CT108 Codex CLI primary-translation candidate (v2.2.0)

Teddy authorized an isolated opt-in official Codex CLI candidate for Japanese-to-Korean primary translation only, followed by one bounded fresh synthetic proof. CT120 remains the running default; Hermes review, adjudication and Japanese/source repair are unchanged. No changes to SIWC, CT121, V2-E, production selectors, scheduling, queues, databases, NAS, Jellyfin, Stage12, publication or existing title artifacts.

Select the backend explicitly, never on failure. Bind prompt, source, session and external model/effort to the private proof; use the unchanged Stage 11 translation validator, never claim a production receipt. Preserve existing timestamp and source ownership. Use the verified dedicated unprivileged CT108 CLI identity, private scratch, read-only tools-off CLI, restricted network and existing 30-second process deadline. One fresh synthetic invocation, no retry, fallback, resume, or further model call. Full-title partition/resume and any production canary remain separate gates.

### Change discipline

- Reuse verified components and evidence; only implement missing core functionality and necessary interfaces. No redundant test or model rerun absent a concrete regression.
- One objective and exit condition at a time. Start with one representative failure and control; enlarge testing only to resolve a material risk. Stop inconclusive test expansion, report evidence, blocker and one next decision. Local defects do not authorize architecture changes.
- No unsupported insertion, deletion, time/identity invention or mandatory per-title human review. No invented numeric quality thresholds; distinguish structural validation from product quality. Material unresolved evidence requires bounded recovery or explicit terminal/quality outcome; details not yet agreed need user decision at relevant gate.
- Only user approval changes architecture, priorities, acceptance or operational scope. Historical checkpoints do not authorize work. Preserve Model Switch inference hold until explicit release.

## Historical design and implementation evidence

The 2026-10-02 JA-master goal and 2026-10-07 whole-title translation direction are retained as history; V2 resolves their ordering as JA master before primary translation.

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
- V2 ordering is approved above; future architecture conflicts require user approval. V2 implementation and product quality remain unverified.

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
