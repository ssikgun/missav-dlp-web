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

Checkpoint: `R6-A — existing persistence and lifecycle boundary audit`
Verdict: **PASS**

Important finding:
- R5 remains frozen and R6 begins as a persistence/lifecycle wrapper around the immutable R1-R5 boundary
- active persistent databases discovered on CT108 are:
  - `/opt/missav-dlp-web/discovery/teddy-discovery.sqlite3`
  - `/opt/missav-dlp-web/discovery/teddy-stage9-media.sqlite3`
  - `/opt/missav-dlp-web/discovery/teddy-discovery-completion-metadata.sqlite3`
- no active Stage11 subtitle-job database currently exists
- Discovery `holdings` remains bounded inventory metadata for verified canonical NAS presence and must not become Stage11 job truth
- the physical NAS filesystem remains authoritative for physical media existence
- Discovery `organizer_jobs` owns Stage9 completion workflow only
- `teddy-stage9-media.sqlite3` owns Stage9 media/Jellyfin retry state only
- completion-metadata DB owns metadata recovery only
- Downloader `.tasks.json` owns Downloader task UUID/progress state and is not a canonical per-title Stage11 identity
- none of the existing persistence mechanisms is an appropriate owner for Stage11 subtitle job truth
- the minimal R6 direction is a separate `/opt/missav-dlp-web/discovery/teddy-subtitle-jobs.sqlite3`
- the initial Stage11 durable owner should be a `subtitle_jobs` table rather than extending Discovery schema v6 or reusing Stage9/media recovery tables
- the logical per-title identity is canonical `dvd_id`, fenced by an immutable source generation/snapshot
- the source generation must include canonical video relative identity plus exact source size and source mtime_ns
- a changed source snapshot creates a new generation rather than silently mutating prior work identity
- repeated attempts for one unchanged source generation update the same logical job and increment bounded attempt metadata
- a separate attempt-history table is not required for minimal R6
- durable state should be kept smaller than the original candidate phase list
- PENDING is a required durable initial state
- SOURCE_DISCOVERY, ALIGNING, TRANSLATING, and VALIDATING are normally transient phases and need not each become durable top-level states
- ASR-ready artifact/source evidence may be durable, but ASR_READY does not imply SOURCE_RELEASED
- SOURCE_RELEASED is separate lifecycle evidence and is primarily relevant to later R7 choreography
- READY_TO_PUBLISH is required durable handoff state because validated semantic work must survive a worker crash
- COMPLETED is a required durable terminal state after safe publication verification
- SKIPPED_EXISTING_KO is a required durable terminal state
- FAILED_RETRYABLE is required with bounded error classification, attempt count, and retry time
- FAILED_FINAL is required for permanent identity, safety, collision, unsupported-route, invalid-artifact, or permanent contract failures
- Stage11 job persistence must never become authoritative for NAS/holdings existence
- the ordinary Stage11 job DB must never store raw JA dialogue, ASR segment text, Hermes request/result dialogue, or KO dialogue
- persisted artifact information should be bounded metadata only: artifact kind/schema, path or cache key, SHA-256, byte size, cue/segment count, source identity, provider/model/version, retention state, and timestamps
- final KO target path/hash must only become completion evidence after safe publication verification
- transient source discovery, ASR, alignment, translation, validation, and prepublication work may be safely rerun from validated persisted source/artifact evidence after a crash
- READY_TO_PUBLISH must survive restart without requiring semantic work to rerun
- post-publication recovery must verify target identity/hash before marking COMPLETED
- R6 owns durable Stage11 retry classification and scheduling metadata; it does not reuse Stage9 retry ownership
- temporary transport/worker/provider/filesystem/lock failures are retryable
- permanent identity/safety/path/collision/artifact/contract failures are final
- exact later R7 attachment point is after verified Stage9 `publish_to_library()` and successful `commit_remote_holding()`, while the source still exists, and before `CompletionSSHMutator.cleanup_source()`
- R7 must preserve `NEVER_DELETE_LOCAL_VIDEO_IF_STAGE9_COPY_NOT_VERIFIED`
- R7 must also keep Stage11 failure non-blocking for normal Stage9 completion
- no R6-essential blocker was found
- before implementation, R6 still needs to freeze the artifact-root/retention policy and stale-RUNNING crash-recovery policy
- the Stage9 runtime marker/handoff commit discrepancy is recorded for later R7 reconciliation and does not block R6
- no source files or databases were changed during this audit

Next planned checkpoint:
`R6-B — freeze minimal Stage11 subtitle job schema, artifact retention, and stale-worker recovery contract`

### R6-B contract progress — INCOMPLETE

Status:
- R6-B persistence/recovery contract is otherwise complete
- remaining blocker is numeric Stage11 worker lease duration and heartbeat cadence
- do not freeze `LEASE_DURATION_SECONDS` or `HEARTBEAT_INTERVAL_SECONDS` until real timing evidence exists

Frozen R6-B direction so far:
- Stage11 job DB: `/opt/missav-dlp-web/discovery/teddy-subtitle-jobs.sqlite3`
- required tables: `schema_migrations`, `subtitle_jobs`, `subtitle_artifacts`
- durable states:
  - `PENDING`
  - `RUNNING`
  - `READY_TO_PUBLISH`
  - `COMPLETED`
  - `SKIPPED_EXISTING_KO`
  - `FAILED_RETRYABLE`
  - `FAILED_FINAL`
- transient RUNNING phases:
  - `SOURCE_DISCOVERY`
  - `ASR`
  - `ALIGNMENT`
  - `TRANSLATION`
  - `VALIDATION`
  - `PREPUBLICATION`
- worker ownership uses `worker_id` plus monotonically increasing `claim_token`
- heartbeat uses the same claim token and extends only `lease_expires_at`
- stale workers are fenced by compare-and-set ownership
- stale RUNNING recovery becomes `FAILED_RETRYABLE / STALE_RUNNING / WORKER_LOST`
- `attempt_count` increments only on a successful RUNNING claim
- artifact root direction: `/opt/missav-dlp-web/discovery/stage11-artifacts/`
- raw subtitle/ASR/Hermes dialogue is forbidden in ordinary job DB and normal logs
- dialogue-bearing recovery data may exist only in confined artifact files
- `READY_TO_PUBLISH` requires a durable, hash-verified KO SRT artifact
- `source_released_at` means only that Stage11 no longer requires the local video for that exact source generation
- `source_released_at` alone never authorizes Stage9 deletion
- numeric artifact retention TTL is intentionally not frozen yet

Lease measurement preparation:
- Stage11 worker heartbeat model: independent in-process heartbeat thread/timer
- phase-boundary-only renewal rejected
- CT108 -> VM122 direct route verified at `192.168.1.134:8091`
- CT108 -> Hermes SSH verified at `192.168.1.230:22`
- VM122 gated-context large-v3 worker restored on port 8091
- restored worker identity:
  - experiment `VAD054_GATED_CONTEXT`
  - VAD threshold `0.54`
  - VAD pad `2500 ms`
  - context `5 s`
  - merge gap `10 s`
  - max window `60 s`
  - model `large-v3`
  - production flag `NO`
- VM122 Qwen 8082 remains running
- temporary Stage11 E4B 8080 process was stopped before restoring Whisper worker
- JUR-750 canary exact source snapshot independently reverified:
  - relative path `JUR/JUR-750/JUR-750.mp4`
  - size `1574462325`
  - mtime_ns `1788438767795262724`
- live NAS source configuration verified:
  - host `192.168.1.201`
  - user `ssikgun`
  - library root `/volume1/video/video2/JAV`
  - SSH key and known-hosts paths exist with expected access
- NAS SSH read-only connectivity PASS
- existing JUR-750 ASR forensic artifact remains present and unchanged
- no subtitle publication, DB write, source deletion, Stage9 mutation, or Jellyfin operation occurred during preparation

ASR measurement runtime diagnostic:
- first `R6-B-MEASURE-ASR` attempt did not reach usable ASR measurement
- failure class was `ASRAudioError`
- root cause was the measurement harness using CT108 system `/usr/bin/python3`
- CT108 system Python has neither NumPy nor PyAV
- the correct Stage11 execution interpreter is `/opt/stage11-stt-venv/bin/python`
- the Stage11 venv contains:
  - NumPy `2.5.2`
  - PyAV `18.1.0`
  - faster-whisper `1.2.1`
  - CTranslate2 `4.8.1`
- with the correct Stage11 venv:
  - `teddy_discovery_asr_audio_smoke.py` PASS
  - `teddy_discovery_asr_remote_smoke.py` PASS
  - `teddy_discovery_asr_transcriber_smoke.py` PASS
- VM122 `192.168.1.134:8091` remained reachable
- therefore the failed measurement is classified as harness/interpreter error, not a Stage11 ASR contract failure
- the retry must use `/opt/stage11-stt-venv/bin/python`
- no DB write, publication, source deletion, or repository source change occurred

R6-B ASR measurement blocker finding:
- the corrected CT108 Stage11 venv removed the first harness/interpreter failure
- subsequent real 600-second requests reached VM122 and loaded large-v3 on GPU
- CUDA, cuBLAS, cuDNN, networking, and worker liveness were not the blocker
- diagnostic instrumentation identified the fail-closed class as `ASRValidationError`
- exact production-source validation branch:
  `ASR segment starts are not nondecreasing`
- this occurred while the measurement was using temporary experiment
  `VAD054_GATED_CONTEXT`
- that gated-context prototype was already documented as pre-production and had unresolved overlap/duplicate handling
- therefore its failure is not evidence that the frozen baseline GPU ASR worker is broken
- the gated-context prototype must not be repaired or promoted as part of R6-B lease measurement
- existing successful baseline remains authoritative:
  - per-VAD large-v3
  - VAD threshold `0.54`
  - speech pad `2500 ms`
  - each VAD region transcribed separately
  - `vad_filter=False`
  - deterministic region-offset restoration
  - JUR-750 full-title baseline completed with 13 chunks, 82 VAD regions, and 166 segments
- R6-B lease timing must use the already-PASS baseline worker path, not the unfinished gated-context experiment
- no Stage11 production source, DB, publication, Stage9 state, or NAS source was changed during diagnostics

Baseline CUDA ASR boundary restoration and real canary:
- existing successful Stage11 remote CUDA architecture remains authoritative
- CT108 `root@downloader` is orchestration/client only
- CT108 uses `/opt/stage11-stt-venv/bin/python`
- CT108 creates bounded 16 kHz mono float32 chunks
- CT108 sends NPY payloads through `RemoteFasterWhisperASR`
- VM122 `teddy@local-llm` owns CUDA execution
- VM122 worker source remains exact commit:
  `dcc835a27e129d051a6dc171b524d1ae6cf6a256`
- VM122 worker venv:
  `/home/teddy/stage11-whisper-v3-venv`
- model cache:
  `/home/teddy/.cache/stage11-faster-whisper`
- remote boundary:
  `http://192.168.1.134:8091`
- CUDA model:
  - `large-v3`
  - `device=cuda`
  - `compute_type=float16`
- baseline worker strategy restored:
  - per-VAD transcription
  - VAD threshold `0.54`
  - speech pad `2500 ms`
  - `vad_filter=False`
  - deterministic region-offset restoration
- Qwen `8082` remained UP
- E4B `8080` remained DOWN
- no SSH-per-request Whisper execution is used
- real JUR-750 first 600-second chunk canary PASS:
  - source copy: `13.405 s`
  - chunk: `0-600000 ms`
  - samples: `9600000`
  - remote CUDA ASR request: `12.316 s`
  - returned segments: `46`
- VM122 `8091` remained reachable after the request
- no DB write, publication, source deletion, Stage9 mutation, or Hermes invocation occurred
- CUDA/Whisper functionality is considered already-established baseline and must not be re-investigated during R6-B unless new evidence directly contradicts it

R6-B full-title baseline ASR timing measurement:
- JUR-750 complete baseline per-VAD large-v3 run PASS
- source transfer: `13.103 s`
- full-title wall time: `102.682 s`
- remote chunks: `13`
- slowest remote chunk: `12.283 s`
- output segments: `166`
- independent observer cadence: `1.0 s`
- observer samples: `102`
- missed observer intervals: `0`
- observer max delay: `9.848 ms`
- observer p50 delay: `0.116 ms`
- observer p95 delay: `0.186 ms`
- observer p99 delay: `0.202 ms`
- max-delay phase: `ASR_REMOTE`
- raw dialogue was neither logged nor stored in the measurement artifact
- no Stage11 job DB write, publication, source deletion, Stage9 mutation, or Hermes invocation occurred
- this is real timing evidence for R6-B lease/heartbeat selection; numeric lease values remain unfrozen until Hermes timing evidence is also measured

R6-B Hermes full-title latency blocker:
- the exact already-PASS R4-E Stage11-Hermes SSH identity was recovered from the original successful command history:
  - `/root/.ssh/id_ed25519_stage11_hermes`
  - `/root/.ssh/known_hosts_stage11_hermes`
- the exact frozen JUR-750 ASR artifact was verified by SHA-256:
  `155c76c25cd1944f6fd85fc4f30b64a05fb34bf236307a7f62d6766ec7133a21`
- one real frozen Hermes semantic invocation was attempted with:
  - provider `openai-codex`
  - model `gpt-5.6-luna`
  - reasoning `xhigh`
  - `166` cues
  - prompt size `36166` bytes
- the request reached the real Hermes/model boundary
- it did not complete within the transport ceiling of `600 s`
- observed failure:
  `HermesV2TransportTimeoutError`
- this is not an SSH/authentication failure and not an ASR failure
- current Hermes transport contract permits at most `600 s`
- current R5 per-title pipeline presents one complete semantic request to the injected semantic boundary
- therefore numeric worker lease/heartbeat values MUST NOT be frozen yet
- simply increasing the measurement timeout beyond the frozen transport ceiling is not an acceptable workaround
- the next work must determine whether bounded semantic batching is required and how to preserve exact cue coverage/order, deterministic timing ownership, fail-closed behavior, and no retry/fallback semantics
- no DB write, publication, source deletion, Stage9 mutation, SSH-key change, or production source-code change occurred

R6-B Hermes batching boundary audit:
- verdict: PASS
- the existing R5 pipeline boundary is:
  `semantic_boundary: Callable[[HermesV2Request], HermesV2Result]`
- `run_subtitle_v2_pipeline()` builds one complete semantic plan and calls the injected semantic boundary exactly once
- the pipeline then validates the returned complete result against the original complete request
- R5 pipeline must remain transport-agnostic and must not import Hermes transport, subprocess, network, database, or publication modules
- bounded Hermes batching therefore belongs behind the existing callable semantic-boundary interface, not inside the R5 pipeline
- the semantic-boundary adapter receives the original complete `HermesV2Request`
- the adapter may partition only the ordered `request.cues` tuple into contiguous bounded batches
- each existing `HermesV2CueInput` object is preserved unchanged inside its batch, including:
  - `cue_id`
  - `external_ja`
  - `stt_ja`
  - `en`
  - `before_context`
  - `after_context`
- no context reconstruction, trimming, rematching, or cross-batch inference is permitted
- each batch is itself a valid `HermesV2Request`
- every batch is attempted exactly once
- no retry, provider fallback, model fallback, or partial-success publication is permitted
- failure or invalid output from any batch fails the whole semantic boundary
- successful batch results are concatenated strictly in batch/request order
- the reconstructed complete `HermesV2Result` must then pass the existing full-request `validate_hermes_v2_result()` against the original unpartitioned request
- duplicate, missing, extra, reordered, or empty-invalid cue output remains fail-closed under the existing contracts
- the R5 route decision, semantic bindings, source/timing ownership, deterministic SRT generation, and publication readiness logic remain unchanged
- the R5 invariant that the pipeline itself calls `semantic_boundary` once remains unchanged; multiple live Hermes calls are an internal implementation detail of the injected adapter
- batching does not change the frozen maximum complete request contract of `512` cues or `4 MiB`; it only creates smaller live model invocations behind that contract
- no numeric batch size is frozen yet
- the full-title `166` cue / `36166` byte / `600 s` timeout proves that one whole-title live invocation is not operationally safe, but does not by itself establish the correct batch size
- numeric batch size must be selected from real latency measurements using the frozen provider/model/reasoning path before implementation
- no source code, Hermes invocation, SSH state, DB, publication, source lifecycle, or Stage9 state changed during this audit

R6-B Hermes 16-cue batch latency measurement:
- exact frozen R4 transport used unchanged
- JUR-750 frozen ASR evidence used in memory only
- contiguous source indices: `64` through `79`
- batch cues: `16`
- prompt bytes: `4589`
- per-invocation timeout: `120 s`
- observed outcome: `PASS`
- wall time: `24.189 s`
- validated result cue count: `16`
- independent observer samples: `24`
- missed observer intervals: `0`
- no raw JA dialogue or Korean translation output was stored or printed
- no retry, fallback, DB write, publication, source deletion, Stage9 mutation, or production-code change occurred
- this measurement alone does not yet freeze the numeric batch size

R6-B Hermes 32-cue batch latency measurement:
- exact frozen R4 transport used unchanged
- JUR-750 frozen ASR evidence used in memory only
- contiguous source indices: `64` through `95`
- batch cues: `32`
- prompt bytes: `9196`
- per-invocation timeout: `120 s`
- observed outcome: `TIMEOUT`
- wall time: `120.101 s`
- validated result cue count: `none because the invocation timed out`
- independent observer samples: `120`
- missed observer intervals: `0`
- comparison evidence:
  - 16 cues: `24.189 s` PASS
  - 32 cues: `120.101 s` `TIMEOUT`
- no raw JA dialogue or Korean translation output was stored or printed
- no retry, fallback, DB write, publication, source deletion, Stage9 mutation, or production-code change occurred
- numeric batch size remains unfrozen in this checkpoint

R6-B Hermes live batch-size freeze:
- numeric live Hermes batch size is now FROZEN at `16 cues`
- evidence:
  - `16` cues / `4589` prompt bytes -> PASS in `24.189 s`
  - `32` cues / `9196` prompt bytes -> TIMEOUT at `120.101 s`
  - full-title `166` cues / `36166` prompt bytes -> TIMEOUT at the transport ceiling of `600 s`
- the selected value is deliberately conservative rather than the largest theoretically possible batch
- every live batch must contain at most `16` contiguous cues
- each existing `HermesV2CueInput` is preserved unchanged inside its batch
- each batch is attempted exactly once
- no retry, provider fallback, model fallback, partial-success publication, context reconstruction, cue rematching, or cross-batch inference is permitted
- batch results must be concatenated strictly in original request order
- the reconstructed complete result must pass the existing full-request `validate_hermes_v2_result()` contract
- the existing R5 pipeline continues to call its injected `semantic_boundary` exactly once
- batching remains an internal implementation detail behind that callable boundary
- R5 route, timing ownership, semantic bindings, deterministic SRT generation, and publication readiness remain unchanged
- the per-live-invocation transport timeout remains governed by the existing frozen R4 transport contract; this checkpoint changes only batch cardinality
- worker lease duration and heartbeat cadence remain UNFROZEN
- they require one real full-title run through the implemented 16-cue batched semantic boundary so total semantic phase timing can be measured
- no production source code, DB, publication, source lifecycle, SSH state, or Stage9 state changed in this checkpoint

R6-B frozen Hermes batching implementation:
- implemented pure semantic-boundary adapter:
  `teddy_discovery_hermes_v2_batching.py`
- frozen live batch cardinality: `16 cues`
- batching module SHA-256:
  `8f1cd3bb197610ca711518bd1fb561285aefd4a7896cf6341f581a7502fdfd40`
- offline smoke:
  `teddy_discovery_hermes_v2_batching_smoke.py`
- batching smoke SHA-256:
  `c80c3bb1827c80ce212b3cb2f4358cebfc72b6a7842ef179983227cd1f2d9add`
- original complete `HermesV2Request` remains the R5 pipeline-facing contract
- adapter partitions only the existing ordered cue tuple into contiguous batches of at most 16
- original `HermesV2CueInput` objects and their context fields are preserved unchanged
- every batch is attempted exactly once
- any execution failure, missing cue, reordered cue, invalid result type, or strict batch-validation failure aborts the complete semantic boundary
- no retry, fallback, partial-success result, context reconstruction, cue rematching, or cross-batch inference was added
- successful batch results are concatenated in original order and revalidated against the original complete request
- adapter contains no transport, subprocess, socket, database, filesystem, publication, or source-lifecycle ownership
- R4 Hermes request/result contract and transport are unchanged
- R5 pipeline is unchanged and still invokes its injected `semantic_boundary` exactly once
- offline batching, Hermes contract, Hermes transport, and R5 pipeline smoke suites PASS
- no live Hermes request, DB write, publication, source deletion, or Stage9 mutation occurred
- worker lease duration and heartbeat cadence remain UNFROZEN

R6-B live full-title 16-cue batched Hermes measurement:
- exact committed batching adapter used
- frozen live batch size: `16 cues`
- JUR-750 frozen ASR evidence: `166 cues`
- expected live batches: `11` (`10 x 16` plus final `6`)
- per-batch frozen transport timeout used: `120 s`
- provider: `openai-codex`
- model: `gpt-5.6-luna`
- reasoning: `xhigh`
- semantic outcome: `BATCH_TIMEOUT`
- complete semantic wall time: `216.787 s`
- attempted batches: `6`
- successful batches: `5`
- slowest successful batch: `21.831 s`
- reconstructed full result cue count: `none`
- per-batch evidence: `1:16c/20.275s/PASS, 2:16c/15.935s/PASS, 3:16c/20.703s/PASS, 4:16c/17.938s/PASS, 5:16c/21.831s/PASS, 6:16c/120.101s/TIMEOUT`
- independent observer samples: `216`
- missed observer intervals: `0`
- no raw JA dialogue or Korean translation output was stored or printed
- no retry, fallback, DB write, publication, source deletion, Stage9 mutation, SSH-key change, or production-code change occurred
- worker lease duration and heartbeat cadence remain unfrozen until this measurement result is reviewed

R6-B failed Batch6 split audit:
- original failed range: indices `80-95`
- original request: `16 cues`, `6074` prompt bytes
- original outcome: `TIMEOUT` at `120.101 s`
- exact failed range was measured as two contiguous 8-cue diagnostic requests
- split evidence: `80-87:8c/4831B/120.101s/TIMEOUT, 88-95:8c/2710B/15.787s/PASS`
- raw JA dialogue and Korean output were not printed or persisted
- this was measurement-only and did not change production code, transport, model, retry policy, DB, publication, source lifecycle, or Stage9
- batched-vs-whole translation quality comparison remains REQUIRED before final semantic strategy approval
- worker lease duration and heartbeat cadence remain UNFROZEN

R6-B failed range 80-87 deeper split audit:
- parent range: indices `80-87`
- parent request: `8 cues`, `4831` prompt bytes
- parent result: `TIMEOUT` at `120.101 s`
- diagnostic split: two contiguous 4-cue requests
- evidence: `80-83:4c/3512B/120.101s/TIMEOUT, 84-87:4c/2786B/9.185s/PASS`
- production batch cardinality remains unchanged
- production transport timeout remains unchanged
- no retry, fallback, DB write, publication, source deletion, Stage9 mutation, or source-code change occurred
- cue-count alone is not accepted as an operational safety predictor
- batched-vs-whole translation quality comparison remains REQUIRED before final semantic strategy approval
- worker lease duration and heartbeat cadence remain UNFROZEN

R6-B Luna whole-file translation provenance audit:
- Teddy independently asked the main Slack-connected Luna/Hermes agent to translate the complete JUR-750 Japanese SRT with natural Korean dialogue and contextual STT correction
- Luna completed the user-visible task in approximately 9–10 minutes
- returned Korean artifact identity:
  - SHA-256: `30a69ed8ce12a345cce0b5cf212bd867f575ea3a5a1ea990db2b5c2ea0fccd75`
  - cue count: `661`
  - cue index sequence: PASS
  - empty cues: `0`
  - `[불명확한 ...]` markers: `3`
  - WhisperJAV metadata cues: `1`
- the expected Japanese input identity is:
  `88edae14fefd7a7838b50c55e4ae4b0b65fb9998e80a147cda81b35412142709`
- that exact Japanese source was not recovered from the current Hermes cache during the bounded audit
- Luna workspace helper:
  `/home/teddy/hermes-workspace/translate_jur750.py`
  - SHA-256:
    `dc4ab6b16364d72e700d424112d7dbdf55b9ce716ba148f1d647e074415c5cb6`
  - valid Python AST
  - no subprocess, requests, urllib, hermes_tools, or OpenAI ownership detected
- Luna temporary patch helper:
  `/tmp/patch_jur750.py`
  - SHA-256:
    `f036445e42558f6fd0a86cf12ea44993b46d8b63660142a3cdeab02f9f651aaa`
  - valid Python AST
  - no subprocess, requests, urllib, hermes_tools, or OpenAI ownership detected
- therefore the 9–10 minute Luna result MUST NOT yet be interpreted as one direct whole-file model invocation
- current evidence is compatible with Luna performing multi-iteration agent reasoning/tool work and writing deterministic helper files, but exact translation provenance remains unproven
- before further shrinking the Stage11 Hermes live batch from 4 cues to 2, the Luna helper implementation must be audited read-only to determine how the 661-cue translation was actually materialized
- the Luna 661-cue output is valuable whole-file quality evidence, but it is not directly comparable to the current 166-segment R6 ASR semantic request because the source cue sequence differs
- batched-vs-whole translation quality comparison remains REQUIRED using equivalent source evidence before final semantic strategy approval
- worker lease duration and heartbeat cadence remain UNFROZEN
- no production source code, transport, model policy, DB, publication, source lifecycle, or Stage9 state changed during this provenance audit

R6-B Luna whole-file helper script audit:
- verdict: PASS
- exact helper/output identities remained unchanged:
  - `translate_jur750.py`:
    `dc4ab6b16364d72e700d424112d7dbdf55b9ce716ba148f1d647e074415c5cb6`
  - `/tmp/patch_jur750.py`:
    `f036445e42558f6fd0a86cf12ea44993b46d8b63660142a3cdeab02f9f651aaa`
  - `JUR-750.ko.srt`:
    `30a69ed8ce12a345cce0b5cf212bd867f575ea3a5a1ea990db2b5c2ea0fccd75`
- translator helper string constants: `16`
- translator Hangul-containing constants: `1`
- patch helper string constants: `17`
- patch helper Hangul-containing constants: `10`
- total helper literal characters: `7406`
- Hangul literal characters: `4220`
- largest string literal: `6871 characters`
- largest Hangul-containing literal: `6871 characters`
- final output cues: `661`
- output cues exactly equal to one individual literal: `1`
- output cues present inside helper literals: `661 / 661` (`100%`)
- no suspicious OpenAI, Hermes, HTTP, subprocess, requests, urllib, Ollama, Qwen, NLLB, chat, or completion call was found in either helper
- provenance classification:
  `TRANSLATION_TEXT_STRONGLY_EMBEDDED_IN_HELPERS`
- therefore the helpers themselves are not translation/model boundaries
- the Korean translation text had already been produced during Luna's agent execution and was embedded into deterministic helper material before final SRT assembly/patching
- the observed approximately 9–10 minute Slack workflow is therefore an end-to-end Luna agent workflow, not evidence of one direct whole-file Hermes/model invocation
- Luna's workflow is architecturally different from the current Stage11 stateless per-request Hermes semantic boundary:
  - Luna retained an ongoing agent/task context across multiple iterations
  - the final helper only materialized translation content already generated during that context
- this provides evidence that a stateful whole-task semantic workflow can successfully materialize a complete `661`-cue subtitle while retaining broader task context
- it does NOT yet prove that this approach has better translation quality than bounded Stage11 batching
- no Stage11 production batching, transport, model, retry, fallback, DB, publication, source lifecycle, or Stage9 policy is changed from this audit
- further `4 -> 2` cue shrinking is paused until the Luna whole-file result is evaluated as a translation-quality baseline
- batched-vs-whole/stateful translation quality comparison remains REQUIRED before final semantic execution strategy approval
- worker lease duration and heartbeat cadence remain UNFROZEN

Next checkpoint:
`R6-B-LUNA-WHOLEFILE-QUALITY-BASELINE-AUDIT — evaluate the exact 661-cue Luna Korean result against the exact 661-cue Japanese source for structural preservation, STT correction behavior, natural Korean continuity, and representative long-context quality before changing the Stage11 semantic execution strategy`

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

### R3 — Deterministic alignment engine — CLOSED / PASS

- Japanese normalization — implemented
- monotonic anchor matching — implemented
- robust affine inference — implemented
- residual/inlier analysis — implemented
- release/content mismatch rejection — implemented
- ASR_ONLY fallback when external evidence is invalid — implemented
- targeted re-ASR hook — deferred; no current evidence justifies implementation

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

### R5 — Stage11 v2 per-title orchestrator — CLOSED / PASS

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
