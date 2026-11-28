# Stage11 subtitle design contract

CONTRACT_VERSION: 2.3.0
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
| Official Codex CLI (CT108) | Exclusive language-model authority for evidence-based Japanese adjudication and justified repair/recovery, Korean translation, joined coherence review, targeted correction, and evidence-aware triage/final review. It does not own cue identity/order, timestamps, routing, or publication. |
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
4. Codex identifies semantic discrepancies and evidence-supported decisions; deterministic code owns identity, accepted source-supported timing, provenance, structural validation. Selectively recheck suspected windows using existing targeted ASR, including gaps detected from audio evidence independent of existing cue list. Demucs only as optional additional evidence for suitable noisy windows, not default replacement or a new mandatory full-title stage. Reuse WX007/WX010/WX011 artifacts if available: historical comparisons inconclusive for transcript accuracy; no automatic adoption of WhisperX, new model or blanket preprocessing.
5. Preserve independently supported speaker turns and sentence boundaries before primary translation, and carry supported turn/line-break information into final JA/KO without fabricating labels, timing, or speaker changes. Existing V2-C source-bound optional speaker-evidence interface and utterance grouping are promoted; missing speaker evidence remains UNKNOWN. Existing pyannote CPU feasibility only; real diarization-to-candidate integration, global speaker consistency, turn accuracy and within-cue utility remain unproven. Do not guess identities/sex/relationships or infer speaker changes from punctuation alone; unknown/overlap retained, no forced splitting. Unavailable diarization alone is not a title failure. Verify representative actual multi-speaker turn preservation and line breaks before claiming this product goal PASS; no compulsory new diarization model or mandatory per-title human review.
6. Materialize source-bound JA master with explicit accepted, rejected and uncertain candidate decisions, stable cue/source identities and timestamps; retain original external JA and raw ASR separately. Preserve plausible dialogue conservatively, no promotion of unsupported synthetic speech. Material unresolved evidence must not silently be called quality PASS; approved bounded fallback or title-level hold, no mandatory manual per-title action. Policy/acceptance specifics need user decision; no flip of AUTO_INSERT alone.
7. Translate the accepted JA master through official CT108 Codex CLI only. Reuse the canonical 64-cue internal part structure with context-preserving transport requests of at most 32 translation-target cues in the current candidate; a part is accepted only after all its validated shards complete. Surrounding source context is evidence, not additional translation targets. Join the full KO result deterministically and perform Codex coherence and evidence-aware source/final review; use overlapping core windows and a compact title reference when whole-title review is too large. Patch only validated material target IDs, retain unaffected text, and recheck source binding, timing, order and coverage. Reuse stage-local receipt/resume and existing CLEAN materialization with necessary adaptations. No blanket rewriting, forced casual speech, or LLM ownership of timestamps.
8. Reuse existing Stage12 validator, no-overwrite publication, title isolation/locks, queue, timer, NAS/Jellyfin path. Keep original external JA, self-generated JA master and final KO distinct (local comparison and NAS original-sidecar requirement preserved, naming/location/lifecycle decision outstanding). Resolve current Git metadata issue before activation. Stage9 unaffected.

### Approved Codex-only Stage11 V2 target — 2026-11-28 (v2.3.0)

The user explicitly directed that all Stage11 language-model work use the official CT108 Codex CLI, and approved aligning this contract with the private Codex-only candidate recorded in the current ACTIVE_WORK. This supersedes the v2.1.0 SIWC opt-in and v2.2.0 primary-translation-only design. Neither Hermes nor SIWC is a dependency, selectable backend or failure fallback in the target Stage11 path; this does not authorize deletion of historical implementations, changing unrelated services, or switching the installed runtime.

- Codex performs Japanese evidence adjudication, justified repair/recovery and targeted re-adjudication, Korean primary translation, assembled coherence review, targeted correction, evidence-aware triage and final review. Whisper and existing evidence adapters provide audio-derived hypotheses; deterministic code owns source identity, routing, timestamps, ordering, structural/evidence validation, assembly and publication eligibility. Codex receives only authorized text/evidence and context, not source video or audio files.
- Use the verified dedicated unprivileged CT108 identity, independent official ChatGPT login, private scratch, restricted network, tools-off CLI and existing sandbox/process containment. Pin and record the selected profile, prompt, source, stage, request IDs, model/effort, and attempt budget; validate exact receipt compatibility before reuse. Candidate evidence used CLI 0.172.0, requested GPT-6-Luna/medium and a hard 30-second per-call process cap; these are observed candidate settings, not an independent effective-provider or universal production quality claim.
- Keep 64-cue canonical translation parts and at most 32 target cues per transport request in the current candidate. Do not apply this fixed partition to every adjudication/review stage. Bound oversized review with overlapping windows and compact title context; targeted patches must match exact allowed IDs. Timeout or invalid output must fail closed with bounded authorized continuation from exact validated completed receipts, never silently switch backend, replay completed calls, or accept partial/invalid results. Production automatic recovery and attempt budgets remain subject to validation and explicit operational approval.
- Keep original audio/ASR, optional validated external JA, JA master, and final KO distinct. Preserve the approved ASR-first HYBRID/ASR-only routing, optional targeted Whisper and selective Demucs evidence, conservative uncertainty, speaker/boundary policy and existing Stage12 protection. No new external transmission or use of unsupported synthetic speech.
- Current evidence is private candidate only: reported synthetic source adjudication/translation/coherence/review and targeted boundary repair, 266-cue translation structural PASS, 11-cue actual retained-text queue rehearsal with bounded review continuation and receipt reuse. Actual full-title media-to-JA/KO processing, real HYBRID/targeted ASR adapter connection, speaker accuracy, installed queue/timer integration, automatic recovery and Stage12 publication are not established by these proofs. Representative full-title quality and operational release gates remain mandatory.
- No production deployment, runtime selector/timer/queue mutation, model invocation, external subtitle transmission, NAS/Jellyfin write or publication is authorized by this documentation amendment. Preserve the installed legacy release and rollback artifacts until a separately authorized validated migration; private candidate outputs are Stage12-ineligible. Historical Hermes/SIWC experiments remain evidence only, not current execution instructions.

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
- V2 ordering is approved above; future architecture conflicts require user approval. The Codex-only V2 candidate has limited private structural and continuation evidence; end-to-end implementation in the installed runtime and product quality remain unverified.

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
