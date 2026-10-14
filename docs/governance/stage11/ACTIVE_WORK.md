# Stage11 subtitle workstream — active work

WORKSTREAM: stage11
TASK_ID: S11-WX006
STATUS: IN_PROGRESS
CONTRACT_VERSION: 1.0.0
REQUIRES_WORKSTREAMS: stage11

## OBJECTIVE

Use saved S11-WX003 through S11-WX005 evidence to define measurable WhisperX comparison limits, investigate the four user-core-confirmed dialogue misses using only persisted intermediate evidence, assess availability of independent evaluation gold, and prepare up to twelve model-outcome-blind held-out candidates if eligible source material exists. Ordinary Stage11 operation continues to target HUMAN_REVIEW_REQUIRED_PER_TITLE=NO.

## APPROVED_SCOPE

- Verify the S11-WX005 user-chat revision SHA and cross-reference its ten core-only judgments without treating Korean phonetic notes as Japanese transcript gold or context as listened.
- Reuse the existing 27-sample manifests, results, audio identities, WX004 comparison, and WX005 judgment revision read-only; distinguish the four targeted WX005 conflict clips from any independent held-out candidates.
- Summarize only supported counts: WhisperX empty output among the existing 13 dialogue-labeled clips; user-heard non-dialogue conflicts among the reviewed controls; transcript/boundary/speaker truth availability. Do not extrapolate the deliberately selected diagnostic set to general or whole-title error rates.
- Investigate clips 003, 005, 006, and 008 using already-saved input ranges, audio preprocessing metadata, VAD regions, selected ASR windows, and intermediate outputs. Assign a cause only when direct saved evidence supports it; otherwise use the approved uncertainty categories.
- Before examining WhisperX outputs for new candidates, freeze and record an objective deterministic selection rule. Select no more than twelve short candidates from existing saved material, avoid all existing 27 core ranges and duplicates, and use eligible subtitle/audio time indexes rather than model outcomes. Keep dialogue presence UNKNOWN. Extract/copy only if needed and only into the private evidence area after identity checks.
- Inspect existing private evidence for independently verified Japanese transcript and timing/speaker gold. Keep model outputs and unverified external JA subtitles as hypotheses.
- Save analysis, selection manifest, and any approved short audio crops only in a private VM122 directory with restrictive permissions. Preserve source hashes and title-absolute time.
- Record findings, limits, and one smallest next-experiment recommendation in the canonical handoff; after analysis, return routing and Stage11 to INACTIVE / TASK_ID: NONE.

## PROHIBITED_SCOPE

- No WhisperX, Whisper, ReazonSpeech, pyannote, Demucs, Hermes, LLM, or other new model inference; no model/package installation or download.
- No full-title FNS-247 ASR, subtitle generation/editing/publication, or transcript/boundary truth created by copying model output or translating phonetic notes.
- Do not modify existing audio, user labels, manifests, saved model results, or prior judgment revisions.
- No Stage11/Stage12 product-code changes; no production service, GPU, database, queue, timer, NAS, or Jellyfin changes.
- No external audio/text transfer, cost-incurring service, or Git inclusion of audio, Japanese source text, private analysis, judgment JSON, or credentials.
- No sample-specific production rule; do not add per-title human review to normal operation or claim automated quality is validated.

## ACCEPTANCE_CRITERIA

- Both required governance checks pass, and this registration is confirmed on the canonical remote before VM122 evidence is inspected.
- The WX005 revision source/hash and its ten core audio identities are verified; original labels and evidence remain unchanged.
- Counts for the existing 27 and the targeted diagnostic subset are reported with their selection limits.
- For each of the four empty outputs, persisted VAD/window/intermediate evidence is reviewed where available; unsupported causality is classified INSUFFICIENT_EVIDENCE or MULTIPLE_POSSIBILITIES.
- Any held-out candidates (0–12) have a pre-frozen selection method, no overlap with prior core intervals, verified provenance, and UNKNOWN dialogue status; no ASR is run on them.
- Transcript/boundary/speaker gold availability is assessed without promoting model output or external text to truth.
- No model calls, production writes, full-title ASR, product changes, subtitle writes, or private Git artifacts occur.
- Handoff is updated, structural governance and diff checks pass, and final router/Stage11 state is INACTIVE / TASK_ID: NONE on the canonical remote.

## EVIDENCE

- The user explicitly approved S11-WX006 with the scope and prohibitions recorded above; ordinary operation remains targeted at HUMAN_REVIEW_REQUIRED_PER_TITLE=NO.
- Canonical base is teddy-subtitle-stage11 at 8a71588ea85a17705b2f3275a8aa95f1982ee9eb; the preceding S11-WX005 closure records the core-only judgment outcome and the unknown transcript/boundary truth.
- Existing handoff records S11-WX003 WhisperX results for 27 samples, including four empty outputs among thirteen dialogue-labeled clips; S11-WX004/WX005 preserved offline comparisons and user listening judgments.
- Saved VAD/window intermediates and independently verified Japanese/boundary gold have not yet been confirmed for this task.

## NEXT_DECISION

Select one smallest follow-up experiment based on the evidence; any model run requires a separate explicit approval.
