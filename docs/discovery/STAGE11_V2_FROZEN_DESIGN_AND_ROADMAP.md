# Stage11 v2 Frozen Design and Roadmap

Status: FROZEN ARCHITECTURE / IMPLEMENTATION IN PROGRESS
Canonical working branch: `teddy-subtitle-stage11`
Design anchor branch: `teddy-subtitle-stage11-doc-anchor`
Baseline commit: `dcc835a27e129d051a6dc171b524d1ae6cf6a256`
Last updated: 2026-09-06 KST

## 1. Purpose

Stage11 v2 generates a safe, synchronized Korean subtitle for a completed JAV title while preserving Stage9 completion semantics and existing safe publication boundaries.

Core principle:

> Trust video/audio/Whisper for timing, use Japanese as the primary meaning source, and let Hermes reconstruct context and produce Korean. Deterministic code owns identity, alignment, timestamps, validation, and publication.

This document is also the canonical roadmap anchor from the current Stage11 work through Stage12 Operations / Hardening. Stage13 or later is not yet frozen and must not be invented without Teddy explicitly defining it.

## 2. Frozen architecture

### Source roles

- Trusted existing canonical KO: protect and skip. Never overwrite automatically.
- Trusted same-media local JA: may translate directly without ASR when synchronization/trust is established.
- Validated external JA: text reference. Intended to run together with Whisper for HYBRID evidence.
- Whisper large-v3: audio/timing reference and second Japanese hypothesis.
- External EN: optional supporting evidence only.
- External KO: ignored as translation truth and must not enter the generated-KO source path.
- No usable JA: ASR_ONLY path.

### Model roles

- Whisper: `faster-whisper large-v3`, CUDA, float16 on VM122.
- Translation/text judge primary: Hermes `gpt-5.6-luna`, provider `openai-codex`, reasoning `xhigh` on CT120.
- Qwen and E4B are not automatic fallbacks. The benchmark selected one primary based on blind semantic quality review.

Blind model benchmark result:

1. Hermes / gpt-5.6-luna
2. Qwen 3.6 35B
3. E4B

Model-selection record SHA256:
`98ac470267c1c54d8f49ffd6d924936993d2cf5804ab5427cdff86ca5aa6a9d1`

### Ownership boundaries

Hermes may output only semantic fields such as:

- cue_id
- repaired_ja
- ko

Hermes must never own or edit:

- start timestamp
- end timestamp
- cue ordering
- canonical identity
- output path
- publication decision

Deterministic code owns all timestamps and safety gates.

## 3. Alignment policy

For external JA + Whisper:

1. normalize Japanese text for matching
2. build monotonic anchors
3. infer per-title timing transform from evidence
4. use robust affine mapping when sufficient
5. use a more complex mapping only when residual evidence requires it
6. never hardcode a title-specific scale, intercept, cue number, phrase, or JUR-750 special case
7. if external content represents a different release/content, reject it and continue ASR_ONLY
8. if external text is useful but a cue is missing/uncertain, targeted re-ASR may be used later

JUR-750 proved that a global offset is insufficient and a robust affine mapping can be sufficient. Those numeric parameters are evidence for that title only and are not production constants.

## 4. Reused frozen v1 components

Prefer reuse over reimplementation:

- `SubtitleCandidate` canonical/external identity contracts
- `SubtitleSSHReader` bounded sibling sidecar reads
- `teddy_discovery_subtitle_text.py` parser and limits
- `teddy_discovery_asr.py` ASR identity/result/word timestamp contracts
- `teddy_discovery_asr_audio.py` 16 kHz mono float32 audio boundary with PTS-gap silence preservation
- remote GPU ASR client/worker
- deterministic ASR artifact serialization and source matching
- Korean guard/completeness guard
- generated SRT boundary
- safe atomic Korean subtitle publisher and collision protection
- Jellyfin refresh/readback boundary when integrated

Do not casually modify frozen v1 modules merely to fit v2. Add isolated v2 contracts/orchestration first and connect only after canaries pass.

## 5. Source lifecycle / Stage9 interaction

Desired flow:

1. CT108 local MP4 download/postprocess completes.
2. Parse canonical dvd_id/destination.
3. Stage11 may consume the local source for ASR before local deletion.
4. Produce and validate immutable ASR artifact.
5. Mark Stage11 source as released only after the ASR artifact/source identity is safe for later work.
6. NAS downloads publish/verify proceeds.
7. CT108 local MP4 may be deleted only when normal downloader publish is verified and Stage11 no longer needs the local source.
8. Stage9 independently moves/copies NAS downloads to canonical JAV destination and verifies it.
9. Stage11 failure must not indefinitely block Stage9 or normal downloader completion.

Invariant:
`NEVER_DELETE_LOCAL_VIDEO_IF_STAGE9_COPY_NOT_VERIFIED`

No direct Jellyfin DB writes. No video re-encode/burn-in.

## 6. Security and privacy invariants

- VM122 receives no NAS credentials.
- Do not put raw dialogue in job/state DB or ordinary HTTP logs.
- Transcript/evidence artifacts belong in bounded spool/cache files with hashes and identity metadata.
- No broad NAS recursive scans.
- Exact/bounded paths only.
- External provider paths/IDs are never guessed from adjacent numeric IDs.
- External subtitle payloads must be bounded, identity-checked, hashed, and parsed through the existing parser.

## 7. Current implementation status

### Completed / accepted

- Stage0-Stage9: CLOSED / PASS.
- Stage10 Holdings Integrity + Duplicate Download Prevention: CLOSED / PASS.
- Stage11: ACTIVE.
- v1 Stage11 baseline at `dcc835a27e129d051a6dc171b524d1ae6cf6a256` confirmed clean before v2 work.
- Whisper word timestamps confirmed.
- SubtitleCat JUR-750 Japanese payload previously retrieved: 661 cues, known SHA256 `88edae14fefd7a7838b50c55e4ae4b0b65fb9998e80a147cda81b35412142709`.
- JUR-750 robust affine alignment feasibility confirmed.
- Blind E4B/Qwen/Hermes semantic benchmark completed and unblinded.
- Hermes selected as primary text judge/translator.
- V2-1A isolated external provider boundary implemented locally in uncommitted files:
  - `teddy_discovery_subtitle_external.py`
  - `teddy_discovery_subtitle_external_smoke.py`
- V2-1A offline review: existing v1 modules unchanged; 4 requested smokes PASS; `git diff --check` PASS.
- V2-DOC1: frozen design/roadmap document synchronized to CT108 at commit `327c29cbabd4269701befe3aeff1aa8a0f7a6760`; PASS.
- V2-DOC2: full Stage11 -> Stage12 project roadmap synchronized to CT108 at commit `3b4f55efe91f52b3fb2c34005a665e37caa6b35b`; PASS.

### Current checkpoint

Checkpoint: `V2-1B-FIX2 — terminal language marker precedence + offline/live canary`
Verdict: **FAIL**

Important finding:
- V2-1B-FIX2 verification did not fully pass
- Stage11 R1 external Japanese provider boundary remains open
- do not advance to hybrid evidence work

Next planned checkpoint:
`V2-1B-FIX2-DIAG — inspect remaining provider failure`

## 8. Stage11 implementation roadmap

### R1 — External Japanese provider boundary

- diagnose/fix current real SubtitleCat HTML parsing failure
- live read-only JUR-750 canary must recover the actual JA href
- verify payload SHA and 661 cues
- freeze provider contract

### R2 — Hybrid evidence contract

Add immutable structures for:

- external JA cue
- Whisper segment/word evidence
- optional EN evidence
- cue identity and neighboring context
- alignment confidence/provenance

No LLM timestamps.

### R3 — Deterministic alignment engine

- Japanese normalization
- monotonic anchor matching
- robust affine inference
- residual/inlier thresholds
- release/content mismatch rejection
- ASR_ONLY fallback when external evidence is invalid
- targeted re-ASR hook only if justified

### R4 — Hermes v2 adapter

New contract separate from old E4B translation adapter.

Input should include bounded semantic/context evidence such as:

- cue_id
- external_ja
- stt_ja
- optional en
- before_context
- after_context

Output:

- cue_id
- repaired_ja
- ko

No timestamps and no extra ownership fields.

### R5 — Stage11 v2 per-title orchestrator

Create a separate v2 orchestration path first. Do not immediately rewrite `run_subtitle_pipeline()`.

Responsibilities:

- trusted KO skip
- local JA direct route where appropriate
- external JA + ASR hybrid
- ASR_ONLY route
- alignment
- Hermes semantic translation
- deterministic timestamp projection
- existing validation/KO guard/SRT generation/publisher reuse

### R6 — State/lifecycle persistence

Candidate states:

- PENDING
- SOURCE_DISCOVERY
- ASR_READY / SOURCE_RELEASED
- ALIGNING
- TRANSLATING
- VALIDATING
- READY_TO_PUBLISH
- COMPLETED
- SKIPPED_EXISTING_KO
- FAILED_RETRYABLE
- FAILED_FINAL

NAS exact sidecar inventory remains final truth. Stage11 job DB is job/cache/retry truth. Do not store raw dialogue in DB.

### R7 — Downloader/Stage9 integration

- invoke Stage11 at the safe local-media lifecycle point
- ensure source release before local deletion
- preserve Stage9 independence
- Stage11 failure must not break normal completion

### R8 — Real semantic canary

- JUR-750 full-path dry/candidate run
- inspect alignment and difficult dialogue cases
- publish only through existing safe publisher after validation
- Jellyfin refresh/readback
- actual playback confirmation

### R9 — Stage11 freeze / production wiring

- smoke suite
- minimal additional real-title canary(s) with ordinary dialogue, not only hard correction cases
- semantic review
- freeze commit/identity
- production wiring

## 9. Stage11 rollout after functional implementation

Do not tune only JUR-750 indefinitely.

Frozen rollout order:

1. 1-title canary
2. 5-title batch
3. quality review
4. small backfill batch
5. Stage11 job/state automation

The 5-title batch should cover, as practical:

- existing KO skip
- local JA/EN text route behavior
- external subtitle route
- ASR route
- BGM/voice mixed content
- normal dialogue
- long silence
- translation completeness
- safe publish
- Jellyfin recognition
- Stage11 failures not affecting Stage9

Stage11 is not functionally CLOSED until the rollout evidence is sufficient to justify production automation.

## 10. Stage12 — Operations / Hardening

Stage12 starts only after Stage11 functional closure. Do not mix Stage12 hardening into Stage11 feature work unless a safety blocker requires it.

### A. Services / process diet

- audit active containers, services, timers, workers
- remove unnecessary always-on daemons
- remove temporary/manual launchers after replacement is proven
- normalize systemd lifecycle

### B. Resource hardening

- CPU peak review
- RAM peak review
- GPU/VRAM phase transition review
- temp disk lifecycle
- artifact/cache retention policy

### C. Reliability

- race conditions
- retries/backoff
- failure isolation
- stale temp cleanup
- worker crash recovery
- partial-state recovery
- Stage9 FAILED long-term accumulation alert
- Subtitle/Stage11 FAILED alert

### D. DB / state durability

- holdings DB consistency policy
- Stage9 media DB backup/readback policy
- Stage11 subtitle/job DB backup/readback policy
- artifact cache retention/validation
- recovery/readback procedure

### E. Security

- VM122 remote ASR endpoint auth/bind/firewall
- harden current plain LAN HTTP boundary where justified
- credentials remain on CT108; never give NAS credentials to VM122
- re-forensic current 123AV stream URL validation and add SSRF/outbound protections if still needed:
  - loopback
  - private IP
  - link-local
  - local/internal hostname
  - unexpected redirect target

Do not broadly redesign unrelated downloader networking without evidence.

### F. Logging / privacy

- raw dialogue logging remains forbidden
- retain useful operational markers only
- reduce noisy logs
- verify secrets are absent from Git/image/logs

### G. Dead code / stale maintenance

- old CPU ASR workaround
- obsolete VAD experiments
- temporary launchers
- deprecated Stage11 branches
- stale TODOs
- `.dockerignore` if still absent/needed
- historical EXDEV gap: verify whether any real gap remains before changing code
- stale Selkies TODO reconciliation
- iPhone Safari completed-file issue only if reproducible

### Stage12 closure target

The Downloader stack should be operationally smaller, recoverable, observable, backed up, and hardened without changing the frozen functional behavior of Stages 0-11.

## 11. After Stage12

No Stage13 has been frozen in existing handoffs.

Therefore after Stage12:

1. close Stage12 with a final handoff/freeze
2. review remaining real user needs and unresolved evidence
3. define a new Stage only with Teddy's explicit agreement
4. do not invent or silently renumber future work

## 12. Project stage map

```text
Stage0-Stage9  CLOSED / PASS
Stage10         CLOSED / PASS — Holdings Integrity + Duplicate Download Prevention
Stage11         ACTIVE        — Korean Subtitle Acquisition / Generation v2
  -> implementation R1-R9
  -> 1-title canary
  -> 5-title batch
  -> quality review
  -> small backfill
  -> job/state automation
  -> functional closure
Stage12         PLANNED       — Operations / Hardening
Stage13+        NOT DEFINED   — requires Teddy approval before definition
```

## 13. Working protocol with Teddy — mandatory

### Reporting

When Teddy pastes terminal/checkpoint output, the first visible token of the response must be exactly one of:

- `PASS`
- `FAIL`
- `INCOMPLETE`

Then report only:

1. verdict
2. short plain-Korean meaning / important finding
3. exactly one next checkpoint

Do not repeat long logs or long theory. Teddy needs to be able to read the result before executing the next command and stop the work if the direction is wrong.

Before giving the next command, summarize the important meaning first.

### Checkpoint documentation — mandatory

After every completed checkpoint (CP), before advancing to another checkpoint:

1. update this canonical document
2. record the CP name and PASS / FAIL / INCOMPLETE verdict
3. record only the important finding or decision
4. record the current blocker, if any
5. record the exact next planned checkpoint
6. if architecture/roadmap changed, update the relevant frozen/roadmap section in the same document

A checkpoint is not considered fully closed until its result is reflected in this document.

Do not let implementation progress get ahead of the documented current state.

### Terminal commands

Always label execution location, e.g.:

- `실행 위치: root@downloader (CT108)`
- `실행 위치: teddy@local-llm (VM122)`
- `실행 위치: root@media (CT112)`
- `실행 위치: root@pve`
- `실행 위치: teddy@hermes-lxc-slack (CT120)`

Give one checkpoint at a time.

Do not give unnecessary SSH/login commands.

Do not provide dangerous interactive shell control such as:

- `exit`
- `logout`
- naked `false`
- interactive `set -e`, `set -eu`, `set -euo pipefail`
- `|| exit 1`
- shell-replacing `exec`
- `kill $$`

Use guarded `if` logic and `ok=1/0` patterns.

Wrong host must print `WRONG_HOST` and do nothing else.

If a lone `>` continuation prompt appears, tell Teddy to press Ctrl+C and rerun a clean block.

### Development discipline

- Inspect exact current source before modifications.
- Reuse frozen/native components.
- Minimal changes, but never omit correctness/safety requirements merely to minimize diff size.
- Codex may implement deterministic tooling/source boundaries and run smokes; it does not replace architecture/final review.
- No title-specific phrase hacks.
- Validation flow: smoke -> minimal real canary -> semantic review -> freeze.
- Actual Jellyfin playback feedback is high-value evidence.
- If a checkpoint fails, fix that slice before advancing the roadmap.

## 14. Canonical rule for future work

Before proposing or implementing a Stage11/Stage12 change, compare it with this document.

If a proposed change conflicts with a frozen item above, stop and explicitly call out the conflict before implementation.

Implementation details may evolve as evidence is collected. Architecture and invariants above must not drift silently.
