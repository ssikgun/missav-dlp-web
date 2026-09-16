# Teddy Downloader / missav-dlp-web Current Handoff

## Current Goal

Stage11/R6 generic Korean subtitle pipeline closure and Stage12 holdings
subtitle rollout readiness.

## Overall Status

- Stage0–10 CLOSED / PASS
- Stage11 CLOSED / PASS
- Stage12 ACTIVE — Holdings Subtitle Rollout + Operations / Hardening
- R6 CLOSED / PASS
- STAGE11_SUBTITLECAT_PROXY_WIRING_FROZEN
- STAGE11_CANARY_ALIGNMENT_CONTRACT_FROZEN
- STAGE11_GENERIC_UNPROJECTABLE_TARGETED_FALLBACK_FIXED
- STAGE11_FIRST_REAL_CONTROLLER_CANARY_PASS
- STAGE11_R6_CLOSED_PASS
- STAGE12_HOLDINGS_SUBTITLE_ROLLOUT_SCOPE_FROZEN
- STAGE12_CP2_DURABLE_ROLLOUT_STATE_PREFLIGHT_PASS
- STAGE12_CP3_ONE_TITLE_ATOMIC_PUBLICATION_CANARY_PASS
- STAGE12_CP4_JELLYFIN_SUBTITLE_RECOGNITION_PASS
- STAGE12_CP5_FIRST_SMALL_BOUNDED_ROLLOUT_BATCH_PASS
- STAGE12_CP6F1_BOUNDED_ALIGNMENT_ASR_ONLY_FALLBACK_PASS
- STAGE12_CP6F4_INVALID_SEMANTIC_PART_RETRY_ISOLATION_PASS
- STAGE12_CP6F6_HERMES_TIMEOUT_TITLE_ISOLATION_PASS
- STAGE12_CP6_FINAL_CLOSURE_PASS
- STAGE12_CP7B_LIVE_64_CUE_BENCHMARK_PASS
- STAGE12_CP7C_ISOLATED_128_CUE_BENCHMARK_PREPARATION_PASS
- STAGE12_CP7D_LIVE_128_CUE_BENCHMARK_PASS
- STAGE12_CP7E_64_VS_128_DECISION_FREEZE_PASS
- STAGE12_CP7F_PRODUCTION_128_CANDIDATE_IMPLEMENTATION_PASS
- STAGE12_CP7G_PRODUCTION_128_ONE_TITLE_LIVE_CANARY_PASS
- STAGE12_CP7I_FIXED128_BOUNDED_ROLLOUT_COMPLETE_FORENSIC
- STAGE12_CP7J_CLOSED_PASS
- STAGE12_CP7K_GENERIC_STATEFUL_FAILURE_DIAGNOSTICS_PASS
- STAGE12_CP7L_SOURCE_AWARE_RUNAWAY_FORENSIC
- STAGE12_CP7M_SOURCE_AWARE_GENERIC_RUNAWAY_VALIDATION_CANDIDATE
- STAGE12_CP7N_FIXED128_FRESH_BOUNDED_ROLLOUT_COMPLETE
- STAGE12_CP7O_FIXED64_BOUNDED_ROLLOUT_PREPARATION

## Completed

- external JA discovery/validation
- affine alignment and safe Hybrid acceptance
- STT-only fallback path
- GPU large-v3 baseline ASR
- durable baseline ASR artifact
- generic ASR source-quality classifier
- targeted second-evidence V1 windows
- targeted GPU/remote path
- durable targeted evidence artifacts
- cross-title calibration: ADN-785 / HSODA-104 / DVDMS-117
- structural/runaway repetition must NOT directly imply OMIT
- generic second-pass evidence projection
- ASR-only + Hybrid stateful semantic review
- deterministic CLEAN materialization
- generic empty Whisper word normalization
- thin generic `run_one_title_stage11(...)` controller
- controller smoke 44/44 PASS
- related targeted/Hybrid/ASR/quality-review regression smoke: PASS
- `build_stage11_live_dependencies(...)` factory
- Flask-free existing-config holding resolver adapter
- first-pass native `run(Namespace)` adapter
- ASR review fresh-session adapter
- Hybrid review fresh-session adapter
- targeted runner source-snapshot adapter
- baseline transcriber composition adapter
- external JA discovery/provider/alignment adapter
- controller + live adapters fake E2E: ASR_ONLY PASS / HYBRID PASS
- `build_stage11_deployment_dependencies(...)` deployment factory
- Flask-free holding resolver using the existing discovery DB contract
- deployment-owned deterministic remote task/session wiring
- CT120 native first-pass preparation and review launcher bridges
- Hybrid originals projection from retained native evidence
- bounded SubtitleCat detail/payload transport composition
- VM122 request timeout `1200` accepted as CANARY_ONLY explicit input
- standalone canary `claim_token=1` retained as STANDALONE_CANARY_ONLY
- deployment + live adapters fake E2E: ASR_ONLY PASS / HYBRID PASS
- deployment smoke: 17/17 PASS
- explicit production semantic policy boundary: legacy 16-cue default plus
  opt-in 128-cue candidate
- policy-bound package generation identity isolates candidate session, local
  staging, remote task, and stateful-part resume keys
- production 128-cue candidate controller smoke: ASR_ONLY PASS / HYBRID PASS
- invalid semantic-part bounded retry and per-title isolation
- Hermes part timeout typed per-title isolation without immediate retry
- Stage12 CP6 final closure: 7/10 PUBLISHED and 3/10 FAILED_RETRYABLE
- explicit SubtitleCat-only Gluetun proxy wiring
- search, detail, and payload use the same configured SubtitleCat proxy
- proxy `http://127.0.0.1:58888` is not a global HTTP proxy
- SubtitleCat proxy offline smoke: PASS
- real-title alignment evidence basis frozen: JUR-750 / HSODA-104
- generic CANARY_ONLY alignment acceptance contract frozen
- initial real generic one-title canary: RAN ONCE and stopped fail-closed at
  Hybrid quality review
- first real controller E2E canary: PASS via ASR_ONLY transport-failure path
- accepted-alignment plus unprojectable-targeted live path: NOT DIRECTLY EXERCISED
- Stage11/R6 final functional closure audit: PASS

## Current Architecture

Generic flow:

TITLE
→ canonical holding
→ baseline ASR
→ external JA attempt
→ safe HYBRID else ASR_ONLY
→ source-quality
→ REQUIRE-only targeted second evidence
→ stateful first-pass translation
→ semantic second-pass review
→ deterministic CLEAN
→ local mechanical report
→ STOP

No automatic publication in the Stage11 controller; Stage12 owns the separate
bounded NAS publication contract.

## Stage12 Holdings Subtitle Rollout Scope — FROZEN

Marker:

`STAGE12_HOLDINGS_SUBTITLE_ROLLOUT_SCOPE_FROZEN`

Stage12 is **ACTIVE**. Its primary goal is to apply the frozen Stage11
pipeline to every owned title that needs Korean subtitles, generate a
validated CLEAN Korean SRT, and safely place it beside the NAS title so that
Jellyfin can use it.

### Holdings and eligibility

- The existing Discovery holdings inventory and DB are the authoritative
  source of owned titles.
- Broad recursive NAS scans are forbidden.
- A title with an existing normal Korean subtitle is deterministically
  skipped and protected; existing KO subtitles must not be overwritten.
- Only eligible titles requiring Korean subtitles enter Stage11 execution.

### Stage11 handoff and durable state

- Stage12 reuses the frozen generic Stage11 controller, route, alignment,
  targeted-evidence, conservative fallback, CLEAN, and provenance contracts.
- Stage11 functionality is not reimplemented, reopened, or retuned.
- Each title must have durable, resumable, idempotent state covering at least:
  `PENDING`, `SKIPPED_EXISTING_KO`, `RUNNING`, `GENERATED`, `PUBLISHED`, and
  `FAILED_RETRYABLE` / `FAILED_TERMINAL`.
- A failed title is isolated from the remainder of a bounded batch, and
  interrupted work can resume without reprocessing completed or skipped
  titles.

### Safe publication and Jellyfin

- Only a valid Stage11 CLEAN SRT may be published.
- Publication is atomic and fail-closed; NAS video files and existing KO
  subtitles are never overwritten.
- Publication outcome and provenance are recorded per title.
- Jellyfin integration uses the normal external-SRT library refresh/rescan
  path when needed; direct Jellyfin DB writes are forbidden.
- Stage12 therefore includes safe NAS subtitle placement and Jellyfin use,
  while Stage11's controller publication boundary remains
  `publication_performed=false`.

### Operations, quality, and rollout

- The existing Operations / Hardening requirements remain Stage12 operating
  requirements: recoverable, observable, backed-up, idempotent, fail-closed,
  and resumable.
- The user-approved quality bar is practical comprehension, not
  commercial-grade translation. Some ASR hallucination or awkward wording is
  acceptable; uncertain KEEP is preferred to false OMIT.
- Rollout is strictly bounded: READ-ONLY holdings inventory/dry-run, then a
  1-title publication canary, then a small bounded batch, and finally the
  eligible holdings rollout.
- Stage12 succeeds only when every eligible holding is accounted for as
  `PUBLISHED` or an explicit `SKIP` / `FAIL`, existing KO subtitles are
  preserved, generated-subtitle provenance is traceable, interrupted runs are
  resumable, Jellyfin can use published subtitles, and unresolved titles are
  visible rather than hidden.

### Stage12 non-scope

- Stage11 feature redesign or reimplementation
- title, catalog-number, cue, or text-specific production hardcode
- existing KO subtitle overwrite
- broad NAS scanning
- direct Jellyfin DB modification
- automatic video modification
- unrelated Downloader feature changes

CP1/CP2 used only bounded inventory, artifact validation, state-store
initialization, and exact-path NAS read/stat. CP3 then performed exactly one
operator-selected HSODA-104 publication canary, and CP4 verified its Jellyfin
recognition. CP5 below records the first serial three-title rollout batch.

## Stage12 CP1 Holdings Subtitle Inventory — PASS

Marker:

`STAGE12_CP1_HOLDINGS_SUBTITLE_INVENTORY_PASS`

CP1 performed one read-only inventory dry-run against the authoritative
Discovery holdings DB. No durable rollout state, controller execution,
subtitle generation, publication, or Jellyfin operation was performed.

### Authoritative source and identity

- DB: `/opt/missav-dlp-web/discovery/teddy-discovery.sqlite3`
- Inventory owner/API: `Stage12HoldingsInventory.run()` in
  `teddy_discovery_stage12_inventory.py`.
- Existing `load_db_state(Path(db_path))` read-only loader was reused; this is
  the same holdings source used by the Stage11 `build_holding_resolver`
  contract.
- Holdings scope is the DB's present `storage_root='jav'` inventory. The
  canonical source identity is `holding_id` plus `jav:<relative_path>`; the
  media identity is the DB `relative_path` under
  `/volume1/video/video2/JAV`.
- The DB contained 173 present canonical holdings, all `MATCHED`, with no
  duplicate DVD-ID or holding path.

### Existing KO and eligibility contract

- Each exact DB holding directory was checked through the existing bounded,
  read-only `SubtitleSSHReader` API; no recursive NAS scan was used.
- Existing subtitle candidates were passed through the existing
  `select_subtitle_source` / canonical target contract.
- Only an exact `<DVD-ID>.ko.srt` candidate whose bytes were read and passed
  strict SRT parsing is `SKIPPED_EXISTING_KO` / existing KO `VALID`.
- No canonical KO sidecar is `ELIGIBLE_NEEDS_KO` / existing KO `ABSENT`.
- Ambiguous, malformed, noncanonical Korean, unavailable, or otherwise
  untrusted subtitle inventory is `UNRESOLVED`; it is never promoted to
  eligible and never overwritten.

### CP1 result

- `TOTAL_HOLDINGS=173`
- `EXISTING_KO=0`
- `ELIGIBLE_NEEDS_KO=172`
- `UNRESOLVED=1`
- Bounded unresolved sample: `JUR-750`, due to the existing subtitle
  contract rejecting the additional noncanonical
  `JUR-750.R6B2-Clean.ko.srt`; the canonical KO state was not silently
  guessed or overwritten.
- Bounded eligible sample begins with `ADN-785`, `ADN-799`, `AKDL-312`,
  `AT-099`, and `AVSA-455`.
- DB writes, NAS writes, Jellyfin writes, publication, controller calls,
  SubtitleCat calls, VM122 calls, and Hermes calls: `0`.

CP1 intentionally created no rollout state DB. CP2 materialized the durable
state and completed the read-only publication preflight described below.

## Stage12 CP2 Durable Rollout State + 1-title Publication Preflight — PASS

Marker:

`STAGE12_CP2_DURABLE_ROLLOUT_STATE_PREFLIGHT_PASS`

CP2 used the CP1 inventory contract and performed no Stage11 controller,
provider, model, publication, Jellyfin, or NAS subtitle write. The only
durable write was the dedicated local Stage12 state store initialization.

### Durable rollout state

- Owner/API: `Stage12RolloutStateStore` in
  `teddy_discovery_stage12_rollout.py`.
- State store: `/opt/missav-dlp-web/discovery/stage12-rollout-state.sqlite3`.
- Writer lock: `/opt/missav-dlp-web/discovery/stage12-rollout-state.sqlite3.lock`.
- Schema: `stage12_rollout_titles` has one canonical `dvd_id` primary key,
  inventory/source snapshot identity, artifact/report/destination provenance,
  timestamps, and transition sequence; `stage12_rollout_events` stores every
  initial state and transition with canonical provenance JSON.
- Supported states: `PENDING`, `RUNNING`, `GENERATED`, `PUBLISHED`,
  `SKIPPED_EXISTING_KO`, `UNRESOLVED`, `FAILED_RETRYABLE`, and
  `FAILED_TERMINAL`.
- Transitions are deterministic and fail-closed. `RUNNING` has explicit crash
  recovery, `PUBLISHED` and `SKIPPED_EXISTING_KO` are terminal, and
  `UNRESOLVED` is never auto-promoted to eligible.
- Re-running CP1 inventory is idempotent: no duplicate title rows or initial
  events are created, and stored holding/source identity drift is rejected.

Actual CP2 initial materialization:

- `TOTAL_STATE_RECORDS=173`
- CP1 `EXISTING_KO=0`, `ELIGIBLE_NEEDS_KO=172`
- `PENDING=172`
- `UNRESOLVED=1`
- `SKIPPED_EXISTING_KO=0`
- all other rollout states: `0`
- Discovery DB writes: `0`; local Stage12 state-store initialization:
  `173` title rows and `173` initial audit events.

### Generic publication canary preflight

- Selector: deterministic artifact-backed selection from eligible inventory;
  no title-specific branch or special treatment exists.
- Selected candidate: `HSODA-104` because its complete existing Stage11
  baseline/CLEAN/report bundle satisfied the generic selector.
- `SOURCE_MEDIA_PATH`:
  `HSODA/HSODA-104/HSODA-104.mp4`
- `DESTINATION_KO_PATH`:
  `HSODA/HSODA-104/HSODA-104.ko.srt`
- `DESTINATION_EXISTS=0`
- CLEAN SHA256:
  `09ad0c4588a52f5eb4d4ef3f48050524cac4b9edad474755ae3a89b500dcfa76`
- report SHA256:
  `7fa9412aabd1c48167fe686df2f8ea92ede7d47c56a5b4d7037d2e6f034ebec3`
- `PUBLICATION_PREFLIGHT=READY`:
  exact source `lstat`, source size/mtime snapshot equality, report-to-CLEAN
  and report-to-baseline binding, strict canonical SRT parse/readback, and
  exact canonical destination absence all passed.

### Publication safety contract frozen for the next checkpoint

- Only a validated Stage11 CLEAN/report/baseline bundle can proceed.
- The CLEAN source artifact is immutable; the NAS video is never modified.
- Only the exact derived `<DVD-ID>.ko.srt` relative destination is allowed;
  path escape and source/report identity mismatch fail closed.
- An existing destination blocks publication; no overwrite is permitted.
- The next publication owner must write a validated temporary file and use
  atomic no-overwrite installation. `PUBLISHED` is recorded only after
  successful atomic installation, destination verification, and equal
  destination/artifact SHA provenance; failed writes never become PUBLISHED.
- Reruns must verify the same provenance and block conflicting content.
- Jellyfin DB direct modification remains forbidden; normal library
  refresh/rescan is the only later Jellyfin operation.

`JUR-750` remains `UNRESOLVED` because the noncanonical
`JUR-750.R6B2-Clean.ko.srt` sidecar was not renamed, deleted, overwritten, or
automatically promoted to canonical KO.

CP3 below used this frozen state/preflight contract and published only the
selected HSODA-104 destination. The next checkpoint is Jellyfin recognition
and safe library-refresh verification.

## Stage12 CP3 One-title Atomic Publication Canary — PASS

Marker:

`STAGE12_CP3_ONE_TITLE_ATOMIC_PUBLICATION_CANARY_PASS`

CP3 performed exactly one operator-selected `HSODA-104` publication canary.
No Stage11 controller, provider, model, SubtitleCat, VM122, Hermes, batch, or
Jellyfin call was made.

### Publication and pre-write validation

- Publication owner/API: existing
  `SubtitleSSHMutator.publish_korean_srt(...)` in
  `teddy_discovery_subtitle_publish.py`; the Stage11 controller was not
  changed.
- Pre-write validation: **PASS** — rollout state was `PENDING`, inventory was
  `ELIGIBLE_NEEDS_KO` with `existing_ko=ABSENT`, source/artifact/report
  identities were valid, strict canonical SRT parsing passed, the report
  title and CLEAN binding matched, the authoritative source snapshot was
  unchanged, the exact canonical destination was absent, no noncanonical KO
  conflict blocked publication, and the path was bounded.
- `CANARY_DVD_ID=HSODA-104`
- source media: `HSODA/HSODA-104/HSODA-104.mp4`
- NAS root: `/volume1/video/video2/JAV`
- exact destination:
  `/volume1/video/video2/JAV/HSODA/HSODA-104/HSODA-104.ko.srt`
  (relative `HSODA/HSODA-104/HSODA-104.ko.srt`)
- source CLEAN:
  `/opt/missav-dlp-web/discovery/stage11-canary-artifacts/HSODA-104/clean-ko-v1.srt`
- mechanical report:
  `/opt/missav-dlp-web/discovery/stage11-canary-artifacts/HSODA-104/stage11-controller-report-v1.json`
- source CLEAN SHA256:
  `09ad0c4588a52f5eb4d4ef3f48050524cac4b9edad474755ae3a89b500dcfa76`
- report SHA256:
  `7fa9412aabd1c48167fe686df2f8ea92ede7d47c56a5b4d7037d2e6f034ebec3`

The writer created a same-directory bounded temporary file, used exclusive
creation, flushed and fsynced the bytes, strictly validated the temporary
SRT, rechecked destination absence, and installed with a no-clobber atomic
hard-link. Race collisions fail closed; existing destinations are never
overwritten. The CLEAN artifact and video/source were not modified.

### Publication result and durable state

- `PUBLICATION_RESULT=PASS`
- destination SHA256:
  `09ad0c4588a52f5eb4d4ef3f48050524cac4b9edad474755ae3a89b500dcfa76`
- source/destination SHA match: **YES**
- destination regular-file and strict canonical SRT readback: **PASS**
- exact HSODA subtitle-directory readback contained only
  `HSODA-104.ko.srt`; source witness remained unchanged
- state transition: `PENDING → RUNNING → GENERATED → PUBLISHED`
- `PUBLISHED` records CLEAN/report/destination identity and atomic publication
  provenance in `/opt/missav-dlp-web/discovery/stage12-rollout-state.sqlite3`
- idempotent second check: **PASS** — state remained `PUBLISHED`, the exact
  destination had the recorded provenance and SHA, no writer was called, and
  no duplicate state/event row was created
- actual NAS write scope: one exact canonical destination plus the writer's
  same-directory temporary file; no other NAS write, video write, or broad NAS
  operation
- Jellyfin DB/write: **0**; Jellyfin recognition is **NOT YET VERIFIED**

Existing KO overwrite protection, source/CLEAN immutability, exact destination
derivation, path-escape rejection, conflict detection, and fail-closed write
failure behavior remain in force. `JUR-750` remains `UNRESOLVED`; its
noncanonical sidecar was not changed.

CP4 below verified Jellyfin recognition for this single title. Small-bounded
and full eligible-holdings publication have not been run.

## Stage12 CP4 Jellyfin Subtitle Recognition Canary — PASS

Marker:

`STAGE12_CP4_JELLYFIN_SUBTITLE_RECOGNITION_PASS`

CP4 verified only the operator-selected `HSODA-104` item. No other title was
refreshed, no NAS file was written, and no Stage11/controller/provider/model
operation was run.

### Exact media and item resolution

- Running Jellyfin Adult library location: `/media/adult`, confirmed through
  the live Jellyfin virtual-folder API and the existing container path
  contract.
- `JELLYFIN_ITEM_ID=20cef6ea376b5323c0eab36342f522c9`
- `JELLYFIN_ITEM_PATH=/media/adult/HSODA/HSODA-104/HSODA-104.mp4`
- `SUBTITLE_FILENAME=HSODA-104.ko.srt`
- `FILESYSTEM_VISIBLE=YES`
- Exact item path matched the authoritative HSODA-104 media identity; the
  exact-path library query returned one item.
- NAS exact readback of `HSODA/HSODA-104/HSODA-104.ko.srt` passed strict SRT
  validation and regular-file checks before and after refresh.
- `FILESYSTEM_SHA256` and CLEAN SHA256 both equal
  `09ad0c4588a52f5eb4d4ef3f48050524cac4b9edad474755ae3a89b500dcfa76`.
- `SHA_MATCH=YES`

### Recognition and bounded refresh

Before refresh, the exact item's `PlaybackInfo` contained no subtitle stream,
so `REFRESH_REQUIRED=YES` and `REFRESH_METHOD=official item-specific API`.
The official item-specific endpoint was used once:

`POST /Items/20cef6ea376b5323c0eab36342f522c9/Refresh`

with non-replacing metadata/image refresh parameters. No library-wide scan or
Jellyfin database SQL operation was used. Bounded polling then found exactly
one matching external subtitle stream:

- `EXTERNAL_SUBTITLE_VISIBLE=YES`
- source path: `/media/adult/HSODA/HSODA-104/HSODA-104.ko.srt`
- `IsExternal=true`
- language: `kor`
- codec: `subrip`
- display title: `Korean - SUBRIP - 외부`
- `RECOGNITION_RESULT=PASS`

The authoritative NAS/video witnesses remained unchanged. `NAS_WRITE=0`,
`JELLYFIN_DB_DIRECT_WRITE=0`, SubtitleCat/VM122/Hermes/controller/provider
calls were `0`, and `JUR-750` was untouched.

CP5 below records the first small bounded Stage12 rollout batch. Existing
Stage11 contracts, conservative fallback policy, canonical KO protection, and
fail-closed publication rules remain unchanged.

## Stage12 CP5 First Small Bounded Rollout Batch — PASS

Marker:

`STAGE12_CP5_FIRST_SMALL_BOUNDED_ROLLOUT_BATCH_PASS`

CP5 selected exactly three titles from the deterministic frozen selector and
processed them serially. The selector required durable state `PENDING`, CP1
eligibility `ELIGIBLE_NEEDS_KO`, `existing_ko=ABSENT`, a valid authoritative
holding/source identity, and excluded `PUBLISHED` and `UNRESOLVED` titles.
The immutable selection was:

- `BATCH_SIZE=3`
- `SELECTED_COUNT=3`
- `SELECTED_DVD_IDS=['ADN-785', 'ADN-799', 'AKDL-312']`
- ordering: canonical `dvd_id` ascending

The generic Stage12 owner was `Stage12BatchRunner` with
`select_pending_batch(...)` in `teddy_discovery_stage12_batch.py`. It reused
the frozen Stage11 controller and owned only bounded selection, per-title
state transitions, artifact validation, exact canonical publication, and
item-specific Jellyfin recognition. No title/cue/text-specific production
logic was added. No automatic retry or concurrency was used.

### Per-title outcomes

- `ADN-785`: Stage11 `PASS`, route `ASR_ONLY`, CLEAN 914 cues, CLEAN SHA256
  `217f10bbc51fc0a712dac0a213d8a79c025e949674833f338d0f6b45438337c1`,
  publication `PASS` to `ADN/ADN-785/ADN-785.ko.srt`, Jellyfin recognition
  `PASS`, final state `PUBLISHED`. Report SHA256:
  `f954c13047057cf2cbd0bef189f065e7605f9db32f6a31bad79f788f411f2293`.
- `ADN-799`: Stage11 `PASS`, route `ASR_ONLY`, CLEAN 422 cues, CLEAN SHA256
  `14cea130f1adc30fc591a4a8a6d3f06e4019dba9cf0740efead5f63e33e9d934`,
  publication `PASS` to `ADN/ADN-799/ADN-799.ko.srt`, Jellyfin recognition
  `PASS`, final state `PUBLISHED`. Report SHA256:
  `7e5633b68457912e8682556f8344ca65a6c9d3280757da3b0969dc98d4b1daea`.
- `AKDL-312`: Stage11 `PASS`, route `ASR_ONLY`, CLEAN 752 cues, CLEAN SHA256
  `d8a02a4747d7d285605243252abdf72573152b98af71fcb78b4af659aa006f30`,
  publication `PASS` to `AKDL/AKDL-312/AKDL-312.ko.srt`; exact destination
  readback and strict SRT validation passed. Initial Jellyfin recognition
  timed out before the bounded polling window, so the title first entered
  `FAILED_RETRYABLE` with the recorded error `Jellyfin external Korean
  subtitle not recognized`. Later read-only verification found the exact
  external Korean stream. Report SHA256:
  `76dcb5bc52384574cff85c66039865469483b71b3582d635b38e80f3b4ea4bfa`.
  The generated CLEAN, destination, source snapshot, and original failure
  history were preserved; no controller, publication, or Jellyfin refresh
  retry was performed.

All three routes were `ASR_ONLY`; external JA outcomes were
`VALIDATION_FAILURE`, `VALIDATION_FAILURE`, and `NO_CANDIDATE`, respectively,
with alignment `NOT_ATTEMPTED`. The three Stage11 controller invocations,
three baseline calls, three external-attempt callbacks, two targeted calls,
three first-pass calls, and three ASR review calls completed within this
single batch; no Hybrid review runner was invoked. Jellyfin used three
item-specific refresh attempts. No other title was processed.

Batch summary:

- `SELECTED=3`
- `PUBLISHED=3`
- `FAILED_RETRYABLE=0`
- `FAILED_TERMINAL=0`
- `SKIPPED=0`
- `UNRESOLVED=0` within the selected batch
- `CONTROLLER_SUCCESS=3`
- `JELLYFIN_RECOGNIZED=3`

At the CP5 evidence snapshot, durable rollout counts were `PENDING=168`, `RUNNING=0`,
`GENERATED=0`, `PUBLISHED=4`, `UNRESOLVED=1`, `FAILED_RETRYABLE=0`,
`FAILED_TERMINAL=0`, and `SKIPPED_EXISTING_KO=0`, across 173 title records.
The local state store has one audited initial state plus three audited
transitions for each selected title, with AKDL-312 additionally retaining one
`PUBLICATION_PROOF_BACKFILLED` audit event and one
`PUBLICATION_RECONCILED` event. No duplicate title state or publication event
was created. A read-only selector dry-run did not reselect the four published
titles or `JUR-750` and returned the next deterministic pending candidates
`AT-099`, `AVSA-455`, and `AVSA-456`.

The publication safety contract remained active: only the three selected
canonical destinations were addressed, existing KO files were not
overwritten, source videos and CLEAN artifacts remained immutable, exact
destination readback matched each CLEAN SHA, and Jellyfin direct database
writes were zero. `JUR-750` remains `UNRESOLVED` and untouched.

The accepted practical quality bar remains content understanding rather than
commercial translation quality. Mixed music/water/noise may cause speech
omissions, and occasional Whisper hallucinations may remain; the user
accepts this quality and prefers uncertain KEEP to false OMIT. This quality
limitation is known and non-blocking for the three completed titles. CP5 is a
full bounded-batch PASS and a larger bounded rollout is ready for separate
authorization.

### CP5R3 AKDL-312 legacy publication-proof backfill and reconciliation

The original `FAILED_RETRYABLE` event was retained unchanged. After offline
smoke validation, the generic `Stage12RolloutStateStore` API recorded one
audited `PUBLICATION_PROOF_BACKFILLED` event using the existing artifact,
report, canonical destination/SHA, exact Jellyfin item/media/subtitle paths,
`external=true`, `language=kor`, `codec=subrip`, and explicit verification
PASS. The state then moved through the existing
`reconcile_published(...)` API to `PUBLISHED` without rerunning the writer,
controller, or Jellyfin refresh. A second reconciliation check was an
`ALREADY_PUBLISHED` no-op with no additional event.

The AKDL-312 final evidence was:

- destination SHA256 equals CLEAN SHA256:
  `d8a02a4747d7d285605243252abdf72573152b98af71fcb78b4af659aa006f30`
- Jellyfin item:
  `b4ae125471a5d7cf704bc1cccac20601`
- Jellyfin media path: `/media/adult/AKDL/AKDL-312/AKDL-312.mp4`
- external subtitle path: `/media/adult/AKDL/AKDL-312/AKDL-312.ko.srt`
- `kor / subrip / external`: PASS
- NAS writes and Jellyfin refreshes during CP5R3: `0`

## Stage12 CP6F1 Bounded Alignment Limit → ASR_ONLY Fallback — PASS

Marker:

`STAGE12_CP6F1_BOUNDED_ALIGNMENT_ASR_ONLY_FALLBACK_PASS`

CP6F1 began after the first CP6 title, `AT-099`, encountered
`teddy_discovery_alignment.AlignmentLimitError` during external-JA alignment.
The cause is the lexical-pair bounded safety limit being exceeded:
`MAX_LEXICAL_PAIR_COMPARISONS=1_048_576`. The cap, alignment algorithm, anchor
selection, acceptance thresholds, Hybrid policy, targeted-ASR policy, and
Stage11 quality tuning were left unchanged.

The smallest safe boundary was `build_external_ja_adapter(...)` in
`teddy_discovery_stage11_live_adapters.py`. Only `AlignmentLimitError` from the
external alignment pipeline is converted to the existing
`ExternalSubtitleValidationError` contract with a generic message. The
controller therefore records external alignment as unavailable and takes the
existing `VALIDATION_FAILURE` / `NOT_ATTEMPTED` / `ASR_ONLY` path. The
`Stage12BatchRunner` generic-exception behavior was not changed.

The AT-099 baseline artifact already exists and is reusable. AT-099 rollout
state is still `RUNNING`; `Stage12RolloutStateStore.recover_running()` was not
applied in CP6F1 and is reserved for the next checkpoint. No CP6 real retry was
performed.

Offline validation passed:

- dedicated `AlignmentLimitError` fallback smoke: PASS
- normal alignment behavior: PASS
- alignment smoke: PASS
- live-adapter smoke: PASS
- deployment smoke: PASS (17/17)
- Stage11 controller smoke: PASS (41/41)
- Stage12 batch smoke: PASS
- Stage12 rollout smoke: PASS
- `py_compile`: PASS
- `git diff --check`: PASS
- Hybrid review calls for the limit fallback: `0`
- existing `AlignmentAcceptanceValidationError` and unrelated unexpected
  programmer exceptions remain fail-closed: PASS
- production title-specific logic: `0`

This checkpoint performed no runtime mutation: AT-099 state mutation `0`, real
controller run `0`, STT `0`, VM122 `0`, Hermes `0`, SubtitleCat `0`, NAS write
`0`, Jellyfin write/refresh `0`, and CP6 restart `0`. The CT108 memory incident
and this `AlignmentLimitError` are separate causes.

## Stage12 CP6F4 Invalid Semantic Part Bounded Retry + Per-title Isolation — PASS

Marker:

`STAGE12_CP6F4_INVALID_SEMANTIC_PART_RETRY_ISOLATION_PASS`

The CP6 retry completed `AT-099` as `PUBLISHED` before the forensic finding on
`AVSA-455`. `AVSA-455` part 9 exposed a generic source-ASR repeated short-unit
hallucination; Hermes produced a repeated Korean output, and the existing
StatefulParts validator correctly rejected it. The validator and all frozen
quality/alignment policies remain unchanged.

The generic resilience owner is
`teddy_discovery_stateful_live_runner.py`. A model-generated semantic part is
now given exactly two maximum attempts: the initial request plus one same-part
retry. An invalid payload is never installed or promoted; the exact remote
regular pending file is rejected and removed before the deterministic same
part query is issued again. Part index, cue range, input SHA, and previously
promoted canonical parts remain unchanged.

After two invalid payloads, the runner raises the typed
`StatefulSemanticOutputValidationRetryExhausted` error. Stage12 reuses its
existing title-failure path, records
`STAGE12_SEMANTIC_OUTPUT_VALIDATION_RETRY_EXHAUSTED` with retry provenance,
transitions only that title to `FAILED_RETRYABLE`, and continues the immutable
serial selection. Unexpected programmer/systemic errors remain
`Stage12BatchSystemicError` and still stop the batch.

Offline validation passed:

- bounded retry smoke: PASS
- invalid first → valid second: PASS; same part/query/input SHA; promote once
- repeated invalid output: PASS; no promote; typed retry exhaustion
- previous promoted parts/resume semantics: PASS
- validator thresholds and production hardcode scan: PASS
- stateful parts smoke: PASS (32/32)
- stateful live runner smoke: PASS (16/16)
- Stage11 controller smoke: PASS (41/41)
- live-adapter smoke: PASS
- deployment smoke: PASS (17/17)
- Stage12 batch smoke: PASS
- Stage12 rollout smoke: PASS
- `py_compile`: PASS
- `git diff --check`: PASS

`AVSA-455` durable rollout state remains `RUNNING`; this checkpoint performed
no recovery or real retry. The actual `recover_running()` and production retry
are reserved for the next separately authorized checkpoint. CP6F4 performed no
controller, STT, VM122, Hermes, SubtitleCat, NAS, or Jellyfin call/write, and
did not restart CP6.

## Stage12 CP6F6 Hermes Part Timeout Per-title Isolation — PASS

Marker:

`STAGE12_CP6F6_HERMES_TIMEOUT_TITLE_ISOLATION_PASS`

The prior production isolation results are durable: `AVSA-455` and `AVSA-456`
are `FAILED_RETRYABLE`, while `BAGR-093` and `BLOR-289` are `PUBLISHED`.
`DASS-884` then reached stateful part `92/117`; its Hermes SSH invocation
exceeded the unchanged `600` second controller timeout.

The narrow owner is
`teddy_discovery_stateful_live_runner.py`. Only
`subprocess.TimeoutExpired` from `_invoke_hermes_part(...)` is converted to
`StatefulLiveRunnerTimeoutError`. Stage12 recognizes that typed error as a
title-level retryable failure and records
`STAGE12_HERMES_PART_TIMEOUT` plus `hermes_timeout.timeout_seconds=600`.
Unrelated `StatefulLiveRunnerError`, unexpected programmer exceptions, state
corruption, malformed commands, and filesystem failures remain systemic and
fail closed.

No same-part retry is performed after timeout. This avoids duplicate remote
Hermes work while the timed-out SSH child may still be running. The existing
`REMOTE_PENDING_RECOVERY` path is unchanged and is used first by the next
operator resume. Previously promoted parts remain preserved.

Offline validation passed:

- Hermes timeout isolation smoke: PASS
- `subprocess.TimeoutExpired` → typed timeout: PASS
- immediate same-part retry count: `0`
- remote pending recovery contract: PASS
- timeout title → `FAILED_RETRYABLE`: PASS
- next title continuation: PASS
- timeout reason/provenance: PASS
- generic runner/programmer errors remain systemic: PASS
- stateful live runner smoke: PASS (16/16)
- bounded semantic retry smoke: PASS
- Stage11 controller smoke: PASS (41/41)
- live-adapter/deployment smoke: PASS (deployment 17/17)
- Stage12 batch smoke: PASS
- Stage12 rollout smoke: PASS
- timeout remains `600` seconds: PASS
- `py_compile`: PASS
- `git diff --check`: PASS

`DASS-884` remains `RUNNING`; no `recover_running()` or actual retry was
performed. CP6F6 made no controller, Hermes, STT, NAS, Jellyfin, or CP6
restart call/write.

## Stage12 CP6 Final Closure — PASS

Marker:

`STAGE12_CP6_FINAL_CLOSURE_PASS`

CP6 is closed without another production retry. The ten selected titles and
final outcomes are:

- `PUBLISHED` (7): `AT-099`, `BAGR-093`, `BLOR-289`, `DLDSS-543`,
  `DOKI-037`, `DOKS-689`, `DROP-141`
- `FAILED_RETRYABLE` (3): `AVSA-455`, `AVSA-456`, `DASS-884`

The final durable Stage12 state across 173 titles is:

`TOTAL=173`, `PUBLISHED=11`, `FAILED_RETRYABLE=3`, `PENDING=158`,
`RUNNING=0`, `UNRESOLVED=1`, `FAILED_TERMINAL=0`, `GENERATED=0`,
`SKIPPED_EXISTING_KO=0`.

The CP6 operating policies are frozen as follows:

1. `AlignmentLimitError` means the lexical-pair safety cap was exceeded. The
   cap and alignment algorithm were unchanged; the existing validation-failure
   contract maps unavailable external alignment to `ASR_ONLY`.
   Implementation commit: `ac39754b95b03a2c7d0b87078d93415a509f902d`.
2. Invalid semantic model output keeps the extreme-repetition validator. The
   same part receives only the initial attempt plus one bounded retry; retry
   exhaustion becomes title-level `FAILED_RETRYABLE`, and the next title
   continues. Implementation commit:
   `cecefa11b30019e579089a1d545f086f1bb2655d`.
3. Hermes part timeout keeps the 600-second limit and never triggers an
   immediate same-part retry. It becomes title-level `FAILED_RETRYABLE`; the
   next resume uses existing remote-pending recovery semantics. Implementation
   commit: `9e9fde3f2777d9386d34ea5ab75219bbf32fe259`.

Per-title isolation was verified operationally: one failed title did not stop
subsequent titles. `AVSA-455` failed after source-ASR extreme repetition and
semantic validation retry exhaustion. `AVSA-456` failed after semantic
validation retry exhaustion. `DASS-884` first timed out at Hermes part `92/117`,
then, after crash recovery and resume, exhausted semantic validation retry and
was preserved as `FAILED_RETRYABLE`. None is retried in this closure.

### CT108 operations incident

Early CP6 encountered CT108 memory/swap pressure and I/O thrashing. The live
expansion was memory `8192 MB → 10240 MB` and swap `512 MB → 1024 MB`.
SSH/pct exec then recovered and I/O/memory pressure dropped while the CP6
process was preserved. The incident was not caused by Stage11 STT CPU load;
STT used VM122 RTX3060 GPU. The 10 GB memory / 1 GB swap configuration remains
the current mixed browser/Selkies/Docker/Downloader baseline and should be
reassessed only in separate operations hardening.

This closure made no source or smoke changes and no production mutation:
Stage11 controller, Hermes, STT, SubtitleCat, NAS, Jellyfin, and recovery or
retry calls were all `0`; production DB mutation was `0`.

## Frozen Policies

- production title/cue/text hardcode 금지
- external JA and Whisper are both fallible
- safe accepted external JA only for Hybrid
- no candidate/fetch/validation/REJECT/UNRESOLVED:
  controller-level ASR_ONLY fallback
- internal invariant/provenance mismatch: fail-closed
- false OMIT worse than uncertain KEEP
- AMBIGUOUS deterministic KEEP
- targeted evidence is evidence only
- Hermes does not own timing, identity, or publication
- no automatic NAS overwrite
- no Jellyfin DB write
- publisher excluded from default controller
- `/var/tmp` artifacts are calibration-only, not production defaults
- SubtitleCat search/detail/payload may use only the explicit deployment proxy;
  NAS, VM122, Hermes, and Discovery DB routing are unchanged

## Stage11 Canary Alignment Contract — FROZEN

Marker:

`STAGE11_CANARY_ALIGNMENT_CONTRACT_FROZEN`

This is the first real Stage11 controller canary contract only.

- scope: `CANARY_ONLY`
- production global default: **NO**
- title-specific policy: **NO**
- no `JUR-750`/`HSODA-104` title branch or name-based policy split
- ambiguity (`UNRESOLVED`) uses the controller's `ASR_ONLY` fallback
- prefer false `ASR_ONLY` fallback over false Hybrid acceptance
- when more real-title evidence accumulates, reassess a separate production
  policy; do not promote this contract implicitly
- initial real `HSODA-104` controller canary: **RAN ONCE; stopped fail-closed at
  Hybrid quality review**
- first completed real `HSODA-104` controller E2E canary: **PASS; ASR_ONLY via
  TRANSPORT_FAILURE**
- accepted-alignment plus valid-targeted-unprojectable live path: **NOT DIRECTLY
  EXERCISED; KNOWN / NON-BLOCKING validation gap**
- Stage11: **CLOSED / PASS**
- publication: **NO**

### Frozen real evidence

The following two real-title results are the cross-title basis. `selected
anchors` maps to the source policy's `anchor_count`; `candidate anchors` is
reported evidence and is not a separate `AlignmentAcceptancePolicy` field.

| title | candidate anchors | selected anchors | external span ms | ASR span ms | scale | median absolute residual ms | inliers at threshold 1000 ms | ratio |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| JUR-750 | 156 | 75 | 7001618 | 7123178 | 1.017323284 | 214.915 | 71 / 75 | 0.946667 |
| HSODA-104 | 99 | 65 | 3505250 | 3504430 | 1.000021754798 | 117.728246 | 61 / 65 | 0.938462 |

### Frozen policy

The source constructor/signature is the exact seven-field frozen dataclass:

```python
residual_threshold_ms = 1000

policy = AlignmentAcceptancePolicy(
    minimum_anchor_count=40,
    minimum_inlier_count=40,
    minimum_inlier_ratio=0.90,
    maximum_median_absolute_residual_ms=250.0,
    minimum_evidence_span_ms=1800000,
    minimum_scale=0.95,
    maximum_scale=1.05,
)
```

`decide_alignment_acceptance` evaluates anchor count, inlier count, external
evidence span, and ASR evidence span first. It then evaluates inlier ratio,
median absolute residual, and scale. A quality failure is
`REJECT_EXTERNAL` with `ASR_ONLY` recommended provenance; an insufficient or
ambiguous evidence result is preserved as `UNRESOLVED` for reporting and the
controller route falls back to `ASR_ONLY`.

Arithmetic/static validation at `residual_threshold_ms=1000`:

- JUR-750: anchor count PASS; inlier count PASS; inlier ratio PASS; median
  residual PASS; external/ASR evidence span PASS; scale PASS.
- HSODA-104: anchor count PASS; inlier count PASS; inlier ratio PASS; median
  residual PASS; external/ASR evidence span PASS; scale PASS.

This policy is a handoff contract, not a source-level production policy
constant.

### Recorded canary values and exact source API map

The first real canary used these explicit values. The existing
artifact/staging roots below came from the initial canary and must be
preserved for future explicitly authorized canary work:

- SubtitleCat proxy: `http://127.0.0.1:58888`
- `remote_task_root`:
  `/home/teddy/.hermes/profiles/subtitle-translator/stage11-controller-canary-v1`
- scope: `CANARY_ONLY`
- Discovery DB explicit injection:
  `/opt/missav-dlp-web/discovery/teddy-discovery.sqlite3`
- `request_timeout_seconds`: `1200` (`CANARY_ONLY`)
- `claim_token`: `1` (`STANDALONE_CANARY_ONLY`)
- `artifact_root`:
  `/opt/missav-dlp-web/discovery/stage11-canary-artifacts`
- `stateful_staging_root`:
  `/opt/missav-dlp-web/discovery/stage11-canary-staging`
- initial failed-canary artifact/staging state: **EXISTING; PRESERVE**
- no canary retry in this handoff checkpoint; existing canary state must not be
  deleted or overwritten

The complete next-run constructor/call map, validated against the current
source signatures, is:

```python
from teddy_discovery_alignment_acceptance import AlignmentAcceptancePolicy
from teddy_discovery_stage11_controller import run_one_title_stage11
from teddy_discovery_stage11_deployment import (
    Stage11DeploymentConfig,
    build_stage11_deployment_dependencies,
)
from teddy_discovery_stage11_live_adapters import build_holding_resolver

config = Stage11DeploymentConfig(
    nas_host="192.168.1.201",
    nas_user="ssikgun",
    nas_key="/opt/missav-dlp-web/teddy-nas-transfer/id_ed25519",
    nas_known_hosts="/opt/missav-dlp-web/teddy-nas-transfer/known_hosts",
    nas_library_root="/volume1/video/video2/JAV",
    asr_base_url="http://192.168.1.134:8091",
    request_timeout_seconds=1200,
    remote_host="192.168.1.230",
    remote_user="teddy",
    ssh_key="/root/.ssh/id_ed25519_stage11_hermes",
    known_hosts="/root/.ssh/known_hosts_stage11_hermes",
    remote_task_root=(
        "/home/teddy/.hermes/profiles/subtitle-translator/"
        "stage11-controller-canary-v1"
    ),
    expected_profile_name="subtitle-translator",
    subtitlecat_timeout_seconds=20.0,
    subtitlecat_proxy_url="http://127.0.0.1:58888",
)

policy = AlignmentAcceptancePolicy(
    minimum_anchor_count=40,
    minimum_inlier_count=40,
    minimum_inlier_ratio=0.90,
    maximum_median_absolute_residual_ms=250.0,
    minimum_evidence_span_ms=1800000,
    minimum_scale=0.95,
    maximum_scale=1.05,
)

deps = build_stage11_deployment_dependencies(
    config,
    acceptance_policy=policy,
    residual_threshold_ms=1000,
    holding_resolver=build_holding_resolver(
        environ={
            "TEDDY_DISCOVERY_DB":
            "/opt/missav-dlp-web/discovery/"
            "teddy-discovery.sqlite3"
        }
    ),
)

run_one_title_stage11(
    "HSODA-104",
    artifact_root=(
        "/opt/missav-dlp-web/discovery/"
        "stage11-canary-artifacts"
    ),
    stateful_staging_root=(
        "/opt/missav-dlp-web/discovery/"
        "stage11-canary-staging"
    ),
    claim_token=1,
    **deps.controller_kwargs(),
)
```

This map is retained as historical provenance for the completed first real
canary. No additional Stage11 run is implied by this closure.

## Stage11 Generic HYBRID Targeted Evidence Wiring Fix — FROZEN

Marker:

`STAGE11_GENERIC_HYBRID_TARGETED_EVIDENCE_WIRING_FIXED`

The first real `HSODA-104` controller canary reached baseline ASR, targeted
second evidence, and the HYBRID first pass: 204 cues across 13/13 completed
parts. It then stopped fail-closed while building the quality review request
with:

`QualityReviewError: targeted second-evidence binding is detached from Hybrid review cues`

Root cause: the controller HYBRID branch passed the validated targeted
artifact to quality review but did not pass `targeted_bindings` to
`prepare_stateful_hybrid(...)`. The preparation therefore used its default
empty targeted binding tuple even though the review projection had targeted
evidence.

The generic fix is:

`validated targeted windows → existing build_targeted_asr_bindings(...) → deterministic tuple → prepare_stateful_hybrid(targeted_bindings=...)`

No title-, cue-, or text-specific production logic was added. The existing
detached/stale targeted-evidence checks, duplicate semantic ownership rejection,
source identity and plan-binding validation, and the quality-review detached
evidence guard remain fail-closed. ASR_ONLY behavior, alignment acceptance
policy, and residual threshold are unchanged. Existing canary artifacts,
staging, and remote session state are preserved.

- subsequent real `HSODA-104` controller E2E canary: **PASS via ASR_ONLY
  TRANSPORT_FAILURE**; accepted-alignment targeted-unprojectable live path was
  not exercised
- Stage11/R6: **CLOSED / PASS**
- publication: **NO**

The subsequent real canary is recorded below; no Stage11 reopening or retry is
implied by this historical section.

## Stage11 Generic Unprojectable Targeted Evidence Fallback — FROZEN

Marker:

`STAGE11_GENERIC_UNPROJECTABLE_TARGETED_FALLBACK_FIXED`

### First real canary history and forensic root cause

The first real `HSODA-104` canary generated and durably reused the baseline
and targeted evidence artifacts. Its Hybrid first pass completed 204 cues over
13/13 parts. Quality review then failed closed because the targeted evidence
was unmapped to the Hybrid review cues:

`QualityReviewError: targeted second-evidence binding is detached from Hybrid review cues`

Forensic conclusion: the valid targeted ASR source evidence did not have a
deterministic association to an accepted external-JA cue in its window. The
existing quality-review detached-evidence guard correctly rejected the
unprojectable evidence. This was an identity-domain/projectability condition,
not a title-specific failure.

The `f91a1f7` generic targeted wiring remains in place:

`validated targeted windows → build_targeted_asr_bindings(...) → deterministic tuple → prepare_stateful_hybrid(targeted_bindings=...)`

### Frozen controller contract

- `VALID + all targeted sources projectable → HYBRID`
- `VALID + any targeted source unprojectable or partial → ASR_ONLY`
- `INVALID / DETACHED / STALE → fail-closed`
- no partial targeted projection and no silent targeted-evidence drop
- accepted external alignment verdict/evidence remains immutable on fallback
- quality-review detached-targeted-evidence guard remains unchanged
- `build_targeted_asr_bindings()` remains unchanged and is the association authority
- no title-, cue-, or text-specific production logic
- existing ASR_ONLY path remains the fallback execution path

The controller completeness check compares every validated targeted artifact
binding with the resulting Hybrid semantic targeted binding using exact window,
source-snapshot, and segment identity, requiring a complete one-to-one source
set. It performs no ordinal, nearest-cue, or arbitrary association.

Offline validation: controller smoke 41/41 PASS; targeted Hybrid, targeted
projection, targeted artifact/runner, ASR source-quality, ASR-only review,
stateful Hybrid, and quality-review regression smokes PASS. `py_compile` and
`git diff --check` PASS.

- real `HSODA-104` controller E2E after this fix: **PASS via ASR_ONLY
  TRANSPORT_FAILURE**
- accepted-alignment plus valid-targeted-unprojectable live path: **NOT DIRECTLY
  EXERCISED; KNOWN / NON-BLOCKING validation gap**
- Stage11/R6: **CLOSED / PASS**
- publication: **NO**

This fallback contract remains closed; observe the live path naturally when it
occurs without reopening Stage11 for a dedicated retry.

## First Real Controller E2E Canary — PASS

The first completed real controller end-to-end canary was `HSODA-104`.

- controller completion: **PASS**
- final route: `ASR_ONLY`
- `baseline_reused`: `true`
- `targeted_reused`: `true`
- `external_ja_outcome`: `TRANSPORT_FAILURE`
- `alignment_outcome`: `NOT_ATTEMPTED`
- CLEAN:
  `/opt/missav-dlp-web/discovery/stage11-canary-artifacts/HSODA-104/clean-ko-v1.srt`
- CLEAN SHA256:
  `09ad0c4588a52f5eb4d4ef3f48050524cac4b9edad474755ae3a89b500dcfa76`
- mechanical report:
  `/opt/missav-dlp-web/discovery/stage11-canary-artifacts/HSODA-104/stage11-controller-report-v1.json`
- report SHA256:
  `7fa9412aabd1c48167fe686df2f8ea92ede7d47c56a5b4d7037d2e6f034ebec3`
- `publication_performed`: `false`
- CLEAN cue count: `265`
- SRT structural errors: `0`
- source quality: `KEEP=264`, `REQUIRE_SECOND_EVIDENCE=1`, `OMIT=0`

The ASR_ONLY stateful first pass completed 265 cues across 17 parts. The
translation session was
`e1a35910-b59d-59b8-87c7-800cb8787c9a`; the second-pass review session was
`5174be4b-a0d3-4f40-97e7-ef573db99221`. Both first pass and review completed.

### User quality acceptance

The user acceptance bar is practical subtitle usability, not commercial-grade
translation: the viewer should understand the work; some ASR hallucination or
awkward wording is acceptable; uncertain KEEP is preferred to false OMIT.

The CLEAN retains some suspected Whisper hallucination, including:

- `시청해 주셔서 감사합니다`
- `다음 영상에서 만나요`
- repeated `안녕히 주무세요`

Trace review shows source-quality classification and second-pass Hermes both
selected KEEP for those cues. This is not a CLEAN materialization bug, and no
aggressive deterministic deletion was applied. Under the stated user bar,
the `HSODA-104` CLEAN is accepted for practical use.

### Live validation boundary

This canary succeeded through `external_ja_outcome=TRANSPORT_FAILURE` and the
existing ASR_ONLY path. It did not directly exercise the new
accepted-alignment + valid-targeted-unprojectable → ASR_ONLY fallback with a
live provider. That remains a **KNOWN / NON-BLOCKING validation gap**. Offline
smoke validation exists; no SubtitleCat retry is implied by this handoff.

- Stage11/R6: **CLOSED / PASS**
- Stage11 controller publication: **NO**
- Stage12 CP3 publication: **HSODA-104 PASS**
- Stage12 CP5: **PASS** — 3 of 3 titles PUBLISHED and Jellyfin-recognized

## Stage11/R6 Final Closure Audit — PASS

Stage11's functional goal is satisfied: the generic controller completed a real
end-to-end title run through ASR, targeted evidence reuse, stateful first-pass
translation, second-pass review, canonical CLEAN SRT, and mechanical report.
The user-approved practical quality threshold is met, and publication was not
part of the Stage11 scope.

No required Stage11 production contract remains incomplete. The generic
ASR_ONLY/HYBRID routes, source-quality handling, targeted evidence validation,
conservative unprojectable fallback, durable CLEAN/report boundaries, and
publication prohibition are implemented and smoke/real-canary validated.

The accepted-alignment + valid-targeted + unprojectable → ASR_ONLY path remains
a `KNOWN / NON-BLOCKING validation gap` in live-provider coverage only. It may
be observed when naturally encountered; it does not reopen Stage11. Production
must continue to fail closed on invalid/detached/stale evidence and use the
conservative ASR_ONLY fallback for valid unprojectable targeted evidence.

The not-yet-provisioned production artifact root, jobs DB, staging root, and
external alignment reuse store are follow-up operational provisioning, not
Stage11 closure blockers.

- Stage11: **CLOSED / PASS**
- R6: **CLOSED / PASS**
- Stage12: **ACTIVE / CP6 CLOSED / PASS** — CP6 selected 10; 7 `PUBLISHED`, 3 `FAILED_RETRYABLE`
- Stage11 controller publication: **NO**
- Stage12 CP3 publication: **HSODA-104 PASS**; CP5: **3/3 PUBLISHED**

## Cross-title Calibration

ADN-785:

- baseline 921
- REQUIRE 4
- lexical/noisy/reaction mixed

HSODA-104:

- baseline 265
- REQUIRE 1
- targeted lexical recovery

DVDMS-117:

- baseline 491
- REQUIRE 2
- targeted lexical recovery
- baseline SHA:
  `5fc3f814162f0152871136bc2901653b574179d85ca050983342994849f7e261`
- targeted SHA:
  `74390dd3a836fd95ba275e1f45f4039d2adbbecfc5f86d8d54f900fec31f6e71`

Cross-title conclusion:

CROSS_TITLE_CALIBRATION_SUFFICIENT

## VM122 Current Worker

- host 192.168.1.134
- port 8091
- endpoint `/v1/asr/transcribe`
- endpoint `/v1/asr/transcribe-targeted`
- model large-v3 / CUDA / float16
- empty-word generic normalization active
- latest deployed gpu worker SHA:
  `ddb39a490d0a44a04d72b51293dea541dc7be4ab212b083fa5b16b336358f927`

## Controller Runtime Contract

- title = canonical DVD-ID only
- artifact_root = explicit caller input
- stateful_staging_root = explicit caller input
- TEDDY_DISCOVERY_DB existing config owner
- valid existing artifact → reuse
- absent → generate
- invalid/detached → fail-closed
- REQUIRE=0 → targeted call 0
- valid targeted artifact → reuse
- CLEAN + report is normal stop point
- publication_performed=false

## Important Runtime Paths

CT108 worktree:

`/opt/missav-pwa-subtitle-stage11`

Discovery DB:

`/opt/missav-dlp-web/discovery/teddy-discovery.sqlite3`

VM122 live worker source:

`/home/teddy/stage11-asr-worker-dcc835a`

Hermes profile:

`/home/teddy/.hermes/profiles/subtitle-translator`

Hermes state DB:

`/home/teddy/.hermes/profiles/subtitle-translator/state.db`

## Deployment Wiring Status

- production connection values read-only preflight: mostly PASS
- deployment-owned callbacks/config are implemented and offline-smoke validated
- canary timeout `1200`: CANARY_ONLY, not a production module default
- `claim_token=1`: STANDALONE_CANARY_ONLY, not a job allocator
- initial failed canary remote Hermes/VM122/Whisper calls: completed before the
  quality-review stop
- first real controller E2E remote ASR/Hermes calls: completed on the
  ASR_ONLY transport-failure path
- accepted-alignment plus unprojectable-targeted live provider path: NOT
  DIRECTLY EXERCISED
- Stage11 controller publication: NOT PERFORMED
- Stage12 CP3 publication: `HSODA-104` PASS; CP5: `3/3` PUBLISHED; full
  eligible-holdings rollout: NOT RUN

## SubtitleCat Network Route

- CT108 direct egress `39.118.143.206`: HSODA-104 search returned HTTP 500
- Gluetun VPN egress `169.150.197.108`: SubtitleCat search returned HTTP 200
- canary proxy endpoint: `http://127.0.0.1:58888`
- Gluetun compose mapping: `127.0.0.1:58888 -> 8888/tcp`
- search, detail page, and subtitle payload share the explicit SubtitleCat-only
  proxy configuration
- global `HTTP_PROXY`, `HTTPS_PROXY`, and `ALL_PROXY` are not configured by
  Stage11

## Unresolved / Not Yet Provisioned

- production Stage11 artifact root
- Stage11 jobs DB
- production staging root
- external JA/alignment durable reuse store
- accepted-alignment plus valid-targeted-unprojectable live canary validation
- bounded publication rollout completion and full eligible-holdings rollout

이 항목들은 필수 구현 결함으로 과장하지 않는다. 현재 다음 milestone에서
필요한 것만 구분한다.

## Stage12 CP7A Isolated 64-Cue Performance Benchmark Harness — PASS

Marker:

`STAGE12_CP7A_ISOLATED_64_CUE_BENCHMARK_HARNESS_PASS`

CP7A prepared an offline-only, benchmark-specific 64-cue partition harness.
Production behavior remains unchanged:

- production `STATEFUL_PART_BATCH_SIZE=16` is unchanged
- production `plan_stateful_parts()`, controller routing, validators,
  resume/session/artifact paths, Stage12 publication, and the 600-second
  Hermes timeout are unchanged
- benchmark policy ID: `benchmark-stateful-cue64-v1`
- benchmark maximum: 64 cues per part
- benchmark input is the exact production semantic package / filtered cue set,
  not a newly reconstructed full ASR cue set
- benchmark root is isolated at
  `/opt/missav-dlp-web/discovery/stage12-performance-benchmark/`
- benchmark layout separates `manifests`, `inputs`, `pending`, `promoted`,
  `reports`, and `logs` by title and policy
- benchmark session identity and remote task identity use a benchmark-only
  namespace/root and cannot reuse the production stateful session identity

The deterministic manifest records policy, input SHA, semantic cue count, part
count, and every ordered part range.  It fails closed on changed input SHA or
policy identity, and it preserves exact cue identity/order with no duplicate
or missing cue acceptance.

The telemetry contract records per-part and total monotonic elapsed time,
Hermes invocations, retries, timeouts, validation failures, resume/recovery
events, cue coverage/order, and raw machine-readable token usage when supplied.
If runtime usage is unavailable, the report records `token_usage: null` and
`TOKEN_USAGE_UNAVAILABLE`; no token estimate is generated.

Offline harness smoke: `42` checks PASS.  Related stateful parts/translator/
controller/live-runner/retry/timeout, Stage11 controller/live-adapter/
deployment, Stage12 batch, and Stage12 rollout smokes PASS.  No live Hermes,
STT, SubtitleCat, NAS, Jellyfin, or production rollout-state operation was
performed by CP7A.  AT-099 / BLOR-289 / DROP-141 live 64-cue execution was
completed in CP7B and is recorded below.

## Stage12 CP7B Isolated 64-Cue Live Performance Benchmark — PASS

Marker:

`STAGE12_CP7B_LIVE_64_CUE_BENCHMARK_PASS`

CP7B ran the benchmark-only 64-cue policy against the three fixed titles.  The
benchmark policy was `benchmark-stateful-cue64-v1`; production
`STATEFUL_PART_BATCH_SIZE=16` remained unchanged.  The benchmark used the
isolated local/remote roots and benchmark-only session identity established by
CP7A.  This closure checkpoint itself performed no new benchmark execution.

### Per-title result

| title | semantic cues | planned parts / Hermes invocations | elapsed seconds | retry | timeout | validation failure | cue coverage / order | result |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| AT-099 | 1471 | 23 / 23 | 4255.821413463913 | 0 | 0 | 0 | PASS / PASS | PASS |
| BLOR-289 | 830 | 13 / 13 | 1802.081057872856 | 0 | 0 | 0 | PASS / PASS | PASS |
| DROP-141 | 173 | 3 / 3 | 929.3162470769603 | 0 | 0 | 0 | PASS / PASS | PASS |

Elapsed-time reference: AT-099 was approximately 70 minutes 56 seconds,
BLOR-289 approximately 30 minutes 02 seconds, and DROP-141 approximately
15 minutes 29 seconds.

### Aggregate result

- titles: `3`
- PASS: `3`
- FAIL: `0`
- total Hermes invocations: `39`
- retry total: `0`
- timeout total: `0`
- validation failure total: `0`
- cue coverage/order failures: `0`
- `CP7B_LIVE_BENCHMARK=PASS`

The fixed 64-cue policy therefore passed `3/3` live benchmark titles.  Against
the existing 16-cue planned-turn counts, the benchmark reduced planned turns
by approximately 75%:

- AT-099: `92` turns → `23` turns
- BLOR-289: `52` turns → `13` turns
- DROP-141: `11` turns → `3` turns

The existing 16-cue executions do not have equivalent elapsed telemetry, so
the benchmark does not claim an exact 75% wall-clock reduction.  Hermes/model
responses did not provide machine-readable token usage; every benchmark report
records `token_usage=null` and `TOKEN_USAGE_UNAVAILABLE`.  No token reduction
percentage is estimated.

### Operational conclusion

The CP7B evidence shows no timeout increase at 64 cues, no validation failure,
no retry, no cue omission, no cue-order error, and normal resume/session
structure.  The 64-cue policy is sufficiently promising as the next
production-optimization candidate, but it is not approved for production
application.  Production remains on the unchanged 16-cue path.

This closure checkpoint changed only this canonical handoff.  It performed no
new benchmark, 128-cue implementation, production source change, production
DB write, NAS/Jellyfin call, or Hermes call.

## Stage12 CP7C Isolated 128-Cue Benchmark Preparation — PASS

Marker:

`STAGE12_CP7C_ISOLATED_128_CUE_BENCHMARK_PREPARATION_PASS`

CP7C prepared a benchmark-only `benchmark-stateful-cue128-v1` policy by
reusing the frozen CP7B partition, validation, pending/promote, telemetry, and
synthetic runner structure. No 128-cue live benchmark was started.

Production and frozen-policy invariants:

- production `STATEFUL_PART_BATCH_SIZE=16`: unchanged
- frozen 64 policy `benchmark-stateful-cue64-v1`: unchanged
- new 128 policy: `benchmark-stateful-cue128-v1`
- 64 and 128 manifests use separate policy-derived session identities and
  local/remote paths; 64 state is not reused or overwritten
- deterministic input SHA and cue boundaries, exact cue coverage/order,
  pending → validation → promote, resume/recovery telemetry, elapsed telemetry,
  and token-usage availability contracts remain fail-closed

Expected 128-cue partition counts for the fixed titles:

- AT-099: `1471` semantic cues, `12` parts
- BLOR-289: `830` semantic cues, `7` parts
- DROP-141: `173` semantic cues, `2` parts
- total expected parts / no-retry synthetic requests: `21`

Validation completed:

- `py_compile`: PASS
- existing 64-cue benchmark smoke regression: `44/44` PASS
- new 128-cue benchmark smoke: `53/53` PASS
- stateful parts smoke: `32/32` PASS
- stateful translator smoke: PASS
- stateful controller smoke: `26/26` PASS
- stateful live-runner smoke: `16/16` PASS
- bounded retry and timeout live-runner smokes: PASS
- three-title synthetic preflight using the staged semantic inputs: PASS
- cue coverage/order: PASS for all 3 titles
- isolated local/remote policy paths: PASS
- synthetic validation/pending/promote/report path: PASS
- `LIVE_HERMES_CALLS=0`
- production calls/writes: `0`
- token usage remains raw mapping only when supplied; synthetic reports record
  `token_usage=null` / `TOKEN_USAGE_UNAVAILABLE`

The CP7C changes were benchmark-only and did not alter the production
controller, live runner, timeout, validator, NAS, Jellyfin, or production DB
behavior.  CP7D below subsequently completed the separately authorized
isolated 128-cue live benchmark.

## Stage12 CP7D Isolated 128-Cue Live Performance Benchmark — PASS

Marker:

`STAGE12_CP7D_LIVE_128_CUE_BENCHMARK_PASS`

CP7D completed the isolated live run for the benchmark-only
`benchmark-stateful-cue128-v1` policy against the same three fixed titles.
The successful run is recorded in
`/opt/missav-dlp-web/discovery/stage12-cp7d-cue128-20260914-123621-live.log`,
with the per-title reports under
`/opt/missav-dlp-web/discovery/stage12-performance-benchmark/`.  The run
verified the expected repository HEAD and branch before execution.

Production and isolation invariants observed during CP7D:

- production `STATEFUL_PART_BATCH_SIZE=16`: unchanged
- frozen 64-cue policy `benchmark-stateful-cue64-v1`: unchanged
- benchmark policy: `benchmark-stateful-cue128-v1`
- Hermes turn timeout: `600` seconds
- `LIVE_HERMES_CALLS=21`
- production calls: `0`
- production writes: `0`
- benchmark-only local/remote roots and policy-derived session identities were
  used

### Actual 128-cue live telemetry

| title | semantic cues | planned parts / Hermes invocations | elapsed seconds | retry | timeout | validation failure | cue coverage / order | token usage | result |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |
| AT-099 | 1471 | 12 / 12 | 3239.958912061993 | 0 | 0 | 0 | PASS / PASS | `TOKEN_USAGE_UNAVAILABLE` | PASS |
| BLOR-289 | 830 | 7 / 7 | 2570.28323274618 | 0 | 0 | 0 | PASS / PASS | `TOKEN_USAGE_UNAVAILABLE` | PASS |
| DROP-141 | 173 | 2 / 2 | 792.2427514139563 | 0 | 0 | 0 | PASS / PASS | `TOKEN_USAGE_UNAVAILABLE` | PASS |

All three `TITLE_RESULT` records and the corresponding report files agree on
the fields above.  CP7D therefore closed `3/3 PASS` with `21` actual Hermes
invocations, `0` retries, `0` timeouts, `0` validation failures, and exact cue
coverage/order for all three titles.  Total elapsed across the three title
reports is `6602.4848962221293` seconds.  The longest observed 128-cue part
was `574.3666827408597` seconds, below the `600`-second timeout but with
limited headroom.

Hermes/model responses did not expose machine-readable token usage.  Every
CP7D report records `token_usage=null` and
`token_usage_status=TOKEN_USAGE_UNAVAILABLE`; no token amount or token
reduction is estimated.

## Stage12 CP7E 64-vs-128 Decision Freeze — PASS

Marker:

`STAGE12_CP7E_64_VS_128_DECISION_FREEZE_PASS`

CP7E read the CP7B/64 and CP7D/128 live `TITLE_RESULT` records and the six
corresponding benchmark reports.  No benchmark source, production source,
production state, NAS, Jellyfin, or rollout state was changed.

### 64-cue source-of-truth audit

The successful CP7B live log and its immutable report both record DROP-141
64-cue elapsed as `929.3162470769603` seconds.  The prior handoff/input value
`929.3987664356828` is not present in the CP7B live `TITLE_RESULT`, final
summary, or benchmark report.  The comparison below therefore uses the actual
log/report value `929.3162470769603`, while the AT-099 and BLOR-289 64-cue
values remain unchanged.

### Per-title comparison

`elapsed delta` is defined as `128 - 64`; a negative value means 128 cues was
faster.  `elapsed % change` uses the same signed direction.  Call reduction is
`64 calls - 128 calls`.

| title | 64 elapsed seconds | 128 elapsed seconds | elapsed delta seconds | elapsed % change | faster policy | 64 → 128 Hermes calls | call reduction | call reduction % |
| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| AT-099 | 4255.821413463913 | 3239.958912061993 | -1015.862501401920 | -23.86995136093095% | 128 | 23 → 12 | 11 | 47.82608695652174% |
| BLOR-289 | 1802.081057872856 | 2570.28323274618 | +768.202174873324 | +42.62861381940810% | 64 | 13 → 7 | 6 | 46.15384615384615% |
| DROP-141 | 929.3162470769603 | 792.2427514139563 | -137.0734956630040 | -14.74992997207897% | 128 | 3 → 2 | 1 | 33.33333333333333% |

128 cues was faster for AT-099 and DROP-141, while BLOR-289 was slower by
`768.202174873324` seconds (`42.62861381940810%`).  The title-level variance
is material and is retained in the decision rather than averaged away.

### Aggregate comparison

| metric | fixed 64 | fixed 128 | 128 versus 64 |
| --- | ---: | ---: | ---: |
| total elapsed seconds | 6987.2187184137293 | 6602.4848962221293 | -384.7338221916000 |
| elapsed % change | — | — | -5.50625130966194% |
| elapsed improvement | — | — | 5.50625130966194% |
| total Hermes calls | 39 | 21 | 18 fewer / 46.15384615384615% |

### Stability comparison

| telemetry | fixed 64 | fixed 128 |
| --- | ---: | ---: |
| PASS titles | 3/3 | 3/3 |
| retry count | 0 | 0 |
| timeout count | 0 | 0 |
| validation failure count | 0 | 0 |
| cue coverage | 3/3 PASS | 3/3 PASS |
| cue order | 3/3 PASS | 3/3 PASS |
| semantic cue counts | 1471 / 830 / 173 | 1471 / 830 / 173 |
| token telemetry | `TOKEN_USAGE_UNAVAILABLE` | `TOKEN_USAGE_UNAVAILABLE` |

All actual invocations equaled planned parts for both policies.  The equal
`3/3 PASS` result demonstrates no observed stability regression in this
sample, but it does not establish production safety for either policy.

### Candidate decision

| candidate | evidence | complexity / rollout safety | freeze decision |
| --- | --- | --- | --- |
| fixed 64 | All 3 titles PASS; lower elapsed for BLOR-289; 39 calls total | Simplest conservative benchmark candidate and more per-part timeout headroom | Retain as validated baseline; not selected as the next optimization candidate |
| fixed 128 | 5.50625130966194% lower aggregate elapsed and 46.15384615384615% fewer calls; all 3 titles PASS; BLOR-289 is 42.62861381940810% slower | Simple fixed policy, but larger parts observed near the 600-second timeout; requires a separately authorized canary | **RECOMMENDED next production-optimization candidate** |
| future adaptive 64/128 | An ex-post faster-policy-per-title selection would be 5834.2827213488053 seconds and 27 calls, but no adaptive run or selector was measured | Highest implementation and rollout complexity; only three titles provide no general decision rule | Defer until broader telemetry and an explicit adaptive design exist |

### Recommendation and scope

Recommendation: freeze **fixed 128** as the next production-optimization
candidate, because it is faster in aggregate and cuts Hermes calls nearly in
half while matching fixed 64 on every observed stability metric.  This is a
candidate recommendation, not a production approval: the BLOR-289 regression,
the limited timeout headroom on the largest observed 128-cue part, and the
absence of token telemetry require a controlled canary and further evidence.
The adaptive option is not selected because its apparent best-of-two result is
an ex-post calculation, not measured adaptive behavior, and its added
complexity reduces rollout safety.

Token result is explicitly `TOKEN_USAGE_UNAVAILABLE`.  Call reduction must not
be represented as token reduction, and no token estimate is permitted.

CP7E changed only this canonical handoff.  Production
`STATEFUL_PART_BATCH_SIZE=16` remains unchanged, and no production policy
value has been changed or applied.

## Stage12 CP7F Production 128-Cue Candidate Implementation — PASS

Marker:

`STAGE12_CP7F_PRODUCTION_128_CANDIDATE_IMPLEMENTATION_PASS`

CP7E is CLOSED / PASS at source `HEAD`
`8cde74598d716bb3dca2e1b61f6b7aefa0353d68` on branch
`teddy-subtitle-stage11`.  CP7F implemented and offline-verified the
production candidate boundary only.  It did not execute a production title,
rollout, Hermes live call, or publication.

### Candidate policy structure

- legacy/default policy: `stage11-stateful-cue16-v1`
- production candidate policy: `stage11-stateful-cue128-v1`
- legacy ownership remains `STATEFUL_PART_BATCH_SIZE=16`; the global default
  was not overwritten
- the part planner now receives an explicit policy/config identity and uses
  that policy's maximum cue count; the default path still plans at 16 cues
  per part
- the candidate is selected explicitly through
  `run_one_title_stage11(..., semantic_policy=...)` and the native runner's
  `--semantic-policy` argument
- benchmark-only policies remain separate from production policy IDs
- package, semantic-part, and result JSON envelopes are unchanged; policy
  metadata is internal/configuration identity, not a new semantic field
- timeout remains `600` seconds, validators remain unchanged, and retry
  behavior remains the frozen bounded policy

### Candidate planner and identity verification

The offline candidate smoke verified the expected deterministic plans:

| semantic cues | expected 128-cue parts | result |
| ---: | ---: | --- |
| 1471 | 12 | PASS |
| 830 | 7 | PASS |
| 173 | 2 | PASS |

The 128 policy is bound before the existing stateful machinery runs by
appending the deterministic policy identity to the package `generation_key`.
The existing UUID5 session derivation then produces a different
`session_id` and input SHA from the unbound legacy package.  The existing
machinery consequently uses distinct:

- local staging directories (`staging_root/session_id`)
- remote task paths (`remote_task_for_session(session_id)`)
- stateful-part resume keys (`session_id`, `input_sha256`, and part index)
- deterministic partition ranges and cue-order validation

The adapter rejects an unbound package when the 128 policy is requested, and
cross-policy plan reuse fails closed.  ASR-only and HYBRID controller smokes
also verified that the policy-bound package remains consistent with existing
review and CLEAN preparation identity.  The default legacy path retains its
unbound package/session identity and its 16-cue behavior.

### CP7F verification and live boundary

- policy smoke: PASS; malformed/missing policy fails closed
- legacy stateful parts smoke: 32/32 PASS
- Stage11 controller smoke: 44/44 PASS
- stateful translator/controller/live-runner/retry/timeout/ASR/HYBRID
  regressions: PASS
- Stage11 live-adapter smoke: PASS
- Stage11 deployment smoke: 17/17 PASS
- Stage12 benchmark/128-policy/batch/rollout regression smokes: PASS
- `py_compile`: PASS
- `git diff --check`: PASS
- benchmark source changes: `0`
- `LIVE_HERMES_CALLS=0`
- `PRODUCTION_WRITES=0`
- `NAS_WRITES=0`
- `JELLYFIN_CALLS=0`
- `ROLLOUT_DB_WRITES=0`
- production policy/state rollout: not performed
- CP7D token telemetry remains `TOKEN_USAGE_UNAVAILABLE`; no token amount or
  token reduction is estimated

The fixed-128 recommendation from CP7E remains a candidate recommendation
for a separately authorized canary.  This CP7F implementation does not
change production policy values or invoke the candidate in production.

## CP7F Changed Files

Only production source, offline smoke, and this existing canonical handoff
were modified.  No new handoff document was created.  The checkpoint source
HEAD remains `8cde74598d716bb3dca2e1b61f6b7aefa0353d68`; no commit or push was
performed.

- policy/planner/controller/adapter source: `teddy_discovery_stateful_policy.py`,
  `teddy_discovery_stateful_translator.py`,
  `teddy_discovery_stateful_parts.py`,
  `teddy_discovery_stateful_controller.py`,
  `teddy_discovery_stateful_live_runner.py`,
  `teddy_discovery_stage11_controller.py`,
  `teddy_discovery_stage11_live_adapters.py`,
  `teddy_discovery_stage11_deployment.py`
- offline smoke coverage: `teddy_discovery_stateful_policy_smoke.py`,
  `teddy_discovery_stage11_controller_smoke.py`
- canonical handoff: `docs/handoff/missav-dlp-web/CURRENT_HANDOFF.md`

## Stage12 CP7G Production 128 One-title Live Canary — PASS

Marker:

`STAGE12_CP7G_PRODUCTION_128_ONE_TITLE_LIVE_CANARY_PASS`

CP7G is **CLOSED / PASS**.  The fixed-128 production candidate completed a
one-title live canary for `AT-099` through the actual Stage11 controller/live
adapter path.  This was a canary only; it was not a production rollout and no
title-specific production branching was added.

### Contract and identity

- policy: `stage11-stateful-cue128-v1`
- route: `ASR_ONLY`
- semantic cue count: `1471`
- planned parts: `12`
- actual maximum cues per part: `128`
- production legacy default: `STATEFUL_PART_BATCH_SIZE=16` unchanged
- candidate session: `4384627a-1cbc-5a0c-844b-c87917fe21c5`
- legacy 16 session: `a7050d19-e17c-500b-89b0-fc427b980583`
- session collision: `NO`
- input SHA identity collision: `NO`
- remote task identity collision: `NO`

### Live execution

- `12/12` semantic parts validated and promoted
- `STATEFUL_LIVE_RUN_COMPLETE=YES`
- `STAGE11_CONTROLLER_END=PASS`
- `CP7G_LIVE_EXECUTION=COMPLETE`
- final cue count: `1471`
- final result SHA256:
  `37e6ed54f9f0ed5e713231085801a634adde88da95c52b478456bc9848b4dc96`
- timeout: `600` seconds unchanged
- validator contract: unchanged
- retry policy: unchanged

### Artifacts and publication boundary

- CLEAN artifact:
  `/tmp/stage12-cp7g-production-canary/artifacts/AT-099/clean-ko-v1.srt`
- `CLEAN_ARTIFACT_VALID=YES`
- controller report:
  `/tmp/stage12-cp7g-production-canary/artifacts/AT-099/stage11-controller-report-v1.json`
- total Hermes live calls: `13`
  - `12` stateful translation part calls
  - `1` ASR quality review call
- token telemetry: `TOKEN_USAGE_UNAVAILABLE`
- `PUBLICATION_PERFORMED=false`
- `NAS_WRITES=0`
- `JELLYFIN_CALLS=0`
- `ROLLOUT_DB_WRITES=0`
- Stage12 production publication/rollout changes: `0`
- CP7G source changes: `0`

The canary confirms that fixed 128 is functional in the real production-path
controller/live adapter structure and is safely separated from legacy 16
identity.  Because only `AT-099` was verified and the result was not
published, CP7G does not promote 128 to the global production default or
execute a full rollout.  NAS, Jellyfin, and rollout state were not affected.

## CP7G Closure

The CP7G live canary is recorded as **CLOSED / PASS**.  Production remains on
the unchanged 16-cue default, and token telemetry remains
`TOKEN_USAGE_UNAVAILABLE`.

## Next Step

CP7J is **CLOSED / PASS** at commit
`d5c09bf7fe09de69b475b1e652ee4e37753cf77d`. CP7K diagnostic instrumentation
is **PASS** and observability-only: production behavior, validator/retry/
timeout contracts, publication, NAS, and Jellyfin behavior are unchanged.
The CP7I rollout result remains only `1/3 PUBLISHED`; fixed 128 is **NOT YET
APPROVED** for general promotion, and production remains on the unchanged
16-cue default.

The one next checkpoint is **CT108 read-only remote artifact forensics** for
the two unresolved evidence boundaries. CP7K performed no live execution;
CT108 must not retry or re-execute a title. Until that checkpoint is
separately completed, no new rollout is authorized.

All next steps must preserve Stage11's frozen contracts and must not reopen
Stage11. The accepted-alignment + valid-targeted-unprojectable live path may
be observed naturally; it remains a KNOWN / NON-BLOCKING gap and does not
imply a dedicated retry.

초기 canary는 QualityReviewError에서 fail-closed 되었고, 이후 첫 완료형
real controller canary는 TRANSPORT_FAILURE 경유 ASR_ONLY로 PASS했다. accepted
alignment + valid targeted unprojectable live path는 아직 직접 검증하지
않았으며, KNOWN / NON-BLOCKING gap으로 유지한다.

## New Conversation Warnings

- Stage11 CLOSED / PASS 상태 유지; 재오픈 금지
- Stage12 ACTIVE / CP7B CLOSED / CP7C PREPARED / CP7D CLOSED / CP7E DECISION
  FREEZE PASS / CP7F CANDIDATE IMPLEMENTATION PASS / CP7G CLOSED / PASS /
  CP7I COMPLETE with `1/3 PUBLISHED` / CP7J CLOSED / PASS / CP7K PASS;
  fixed 128 is not the global production default
- production `STATEFUL_PART_BATCH_SIZE=16` unchanged; no production policy
  change has been applied
- the only next checkpoint is CT108 read-only remote artifact forensics; do
  not blind-retry or re-execute CP7I failures
- CP7K performed no live execution and no production writes
- 작품별 튜닝으로 되돌아가지 않기
- ADN/JUR/HSODA/DVDMS 특정 production logic 금지
- old canonical KO subtitle overwrite 금지
- no unbounded or blind retries; only the frozen generic bounded retry
- Hermes timeout does not trigger immediate same-part retry; resume uses remote pending recovery
- no broad NAS scan
- no automatic publication
- controller/result가 timing authority를 Hermes에 넘기지 않도록 유지

## CP7I Fixed-128 Bounded Rollout — COMPLETE / 1 of 3 PUBLISHED

`STAGE12_CP7I_FIXED128_BOUNDED_ROLLOUT_COMPLETE_FORENSIC`

CP7I is **COMPLETE** as an execution checkpoint, but the rollout outcome is
only **1/3 PUBLISHED**. This records the bounded result and does not approve
general fixed-128 promotion.

### Frozen execution contract and result

- Selected titles: `DVAJ-754`, `DVAJ-757`, `DVDES-795`; sessions were
  `0b7b50f8-7ba0-5d2a-84ce-217a40250547`,
  `05c97ddf-6587-5041-b5c0-5265862fe35a`, and
  `bef988b4-5878-51c9-a1cc-24c03311fbbd` respectively.
- Policy: fixed-128 (`stage11-stateful-cue128-v1`); production default
  `STATEFUL_PART_BATCH_SIZE=16` remained unchanged.
- `HERMES_TURN_TIMEOUT_SECONDS=600` and
  `STATEFUL_PART_MODEL_MAX_ATTEMPTS=2` remained unchanged. Validator, retry,
  timeout, and publication contracts were not modified.
- CP7I summary: `selected=3`, `published=1`, `failed_retryable=2`,
  `failed_terminal=0`.
- No 64-cue fallback, timeout increase, validator relaxation, retry increase,
  blind retry, or re-execution was performed during forensic review.

### DVAJ-754 — FAILED_RETRYABLE

- Session `0b7b50f8-7ba0-5d2a-84ce-217a40250547`; input had 235 cues and the
  deterministic plan had 2 parts. Part 1 was
  `asr-000001..asr-000128`.
- Both attempts reached the model boundary: the live log records
  `MODEL_RC=0`, `REMOTE_MODEL_STEP_RESULT=1`, and the same remote pending
  path, followed by `INVALID_PENDING_REJECTED=1`. The controller then raised
  `StatefulSemanticOutputValidationRetryExhausted` after 2 attempts.
- The exact validator rejection available in durable evidence is:
  `StatefulPartsValidationError` while installing the pending semantic part
  for part 1. The live log and rollout DB retain only the typed exhaustion
  error and do not retain the inner `StatefulPartsValidationError` message.
  The remote pending payload was removed after each rejection, and no invalid
  payload is present in the local staging directory.
- The local input artifact
  `/tmp/stage12-cp7i-fixed128-rollout/staging/0b7b50f8-7ba0-5d2a-84ce-217a40250547/stage11-semantic-input.json`
  has the expected input SHA
  `2a74fee94009febef0f761ac3bc07d5470cb9db229fe2b18b25aa8301b8a292d`,
  235 ordered unique cue IDs, and the expected part-1 range. This confirms
  the input plan only; it does not validate the model output.
- Model output existence: **YES at the controller read/reject boundary**.
  JSON parse success/failure: **UNPROVEN**. Cue count, cue IDs, missing,
  duplicate, order, unexpected cue, malformed field, `repaired_ja`, `ko`,
  part/session/input SHA, and other inner validator predicates:
  **UNPROVEN**. Reasoning text was not used.
- Both attempts had the same observable rejection category, part, and range.
  Whether their hidden inner validator reason was identical or different is
  **UNPROVEN**. Publication and Jellyfin were not run.

### DVDES-795 — FAILED_RETRYABLE

- Session `bef988b4-5878-51c9-a1cc-24c03311fbbd`; input had 1,594 cues and the
  deterministic plan had 13 parts. The first requested range was
  `asr-000001..asr-000130`.
- Invocation start timestamp: **NOT RECORDED** in the live log, DB, or local
  artifacts. The last local input persistence was
  `2026-09-14 19:11:27.485054644 KST`; the DB failure event was
  `2026-09-14 19:21:28.886951 KST`, a delta of `601.401897` seconds. This is
  input-persistence-to-failure, not a claimed invocation elapsed time.
- Controller timeout remained exactly `600` seconds. The source uses
  `subprocess.run(..., timeout=600)` and raises
  `StatefulLiveRunnerTimeoutError: Hermes part invocation exceeded controller
  timeout`; the DB provenance also records `timeout_seconds=600`.
- The live log shows the remote Hermes session was reached and started, but
  there is no `MODEL_RC`, `REMOTE_MODEL_STEP_RESULT`, validated pending part,
  canonical part, or final result for this title. Validation was therefore
  **NOT REACHED**; publication and Jellyfin were not run.
- Local post-run session state contains only `stage11-semantic-input.json`;
  no pending, canonical, result, or resume artifact exists locally. Remote
  task/session state at and after timeout, pending output at timeout, later
  Hermes output/process state, and remote resumeability are **UNPROVEN**.
  The read-only network probe could not connect to CT120 (`Operation not
  permitted`), so this boundary is explicitly:
  `NETWORK_FORENSIC_DEFERRED_TO_CT108`.

### DVAJ-757 — PUBLISHED baseline

- Session `05c97ddf-6587-5041-b5c0-5265862fe35a`; 757 cues; all 6/6 fixed-128
  parts were validated and promoted, and the final semantic result was
  complete with 757 cues.
- Route was `ASR_ONLY`; publication PASS; Jellyfin recognition PASS with
  subtitle language `kor`. The clean artifact SHA256 was
  `07104e874371acc10ea2c495712e421ec728b6a4d29bd81eb0f9c98f783c448f`.
- This is a success baseline only. It confirms the fixed-128 path and the
  unchanged validator/retry/timeout contract on this title; it does not
  establish a general 128-cue production default.

### Forensic decisions

- 128-specific failure evidence: **UNPROVEN**.
- Generic semantic validation failure: **YES** (`DVAJ-754`).
- Generic timeout failure: **YES** (`DVDES-795`).
- Publication path failure: **NO**. The failed titles stopped before
  publication, while DVAJ-757 passed publication and Jellyfin verification.
- Title-level isolation: **PASS**. One title published successfully and the
  two failures were isolated with publication/Jellyfin not run.
- Fixed-128 general promotion: **NOT YET APPROVED**.
- Production default 16: **UNCHANGED / YES**.

Forensic-review counters were all zero: `LIVE_HERMES_CALLS=0`, `NAS_WRITES=0`,
`JELLYFIN_CALLS=0`, `ROLLOUT_DB_WRITES=0`. These counters describe this
read-only forensic pass; no new rollout action was taken.

### Historical CP7I checkpoint

**CT108 read-only remote artifact forensics:** recover the CT120 task/session
metadata and retained validator/pending-output evidence needed to resolve the
DVAJ-754 inner rejection and DVDES-795 post-timeout state. No retry,
re-execution, fallback, timeout change, validator change, or publication is
authorized by this checkpoint.

## CP7J / CP7K Closure — PASS

`STAGE12_CP7J_CLOSED_PASS`

CP7J is **CLOSED / PASS** at commit
`d5c09bf7fe09de69b475b1e652ee4e37753cf77d` on branch
`teddy-subtitle-stage11`.

`STAGE12_CP7K_GENERIC_STATEFUL_FAILURE_DIAGNOSTICS_PASS`

CP7K is **PASS** as an observability-only checkpoint. It changes no
production decision or behavior. The fixed-128 candidate remains unapproved
for general promotion, and production default `STATEFUL_PART_BATCH_SIZE=16`
is unchanged.

### Diagnostic instrumentation

- Existing `StatefulPartsValidationError` instances now carry a machine-readable
  `reason_code` without changing the exception hierarchy or validation rules.
  Existing validator predicates are exposed as `JSON_PARSE_FAILURE`,
  `SCHEMA_FAILURE`, `SESSION_ID_MISMATCH`, `INPUT_SHA256_MISMATCH`,
  `PART_INDEX_MISMATCH`, `FIRST_CUE_ID_MISMATCH`,
  `LAST_CUE_ID_MISMATCH`, `CUE_COUNT_MISMATCH`, `MISSING_CUE_ID`,
  `DUPLICATE_CUE_ID`, `UNEXPECTED_CUE_ID`, `CUE_ORDER_MISMATCH`,
  `INVALID_REPAIRED_JA`, `INVALID_KO`, `INVALID_FIELD`, or
  `OTHER_VALIDATOR_PREDICATE`.
- Each rejected semantic attempt logs one bounded
  `SEMANTIC_VALIDATION_REJECTED=<reason>` marker with `PART_INDEX`,
  `ATTEMPT`, `SESSION_ID`, and `INPUT_SHA256`. Model output contents are not
  logged by this instrumentation.
- Each Hermes semantic invocation logs
  `HERMES_INVOCATION_START_EPOCH`, `HERMES_INVOCATION_END_EPOCH`,
  `HERMES_INVOCATION_ELAPSED_SECONDS`,
  `HERMES_INVOCATION_TIMEOUT_SECONDS`, and
  `HERMES_INVOCATION_RESULT=PASS|TIMEOUT|FAIL`. The timeout remains exactly
  `600` seconds, including the timeout path.
- Validation failure and timeout paths log bounded pending path/existence/
  size evidence, local pending evidence, result existence, and
  resume/promoted artifact existence. Unknown remote state remains explicitly
  `UNKNOWN` when it cannot be safely observed; artifact contents are never
  dumped.
- The existing validator, bounded retry count, cue contract, session/resume
  identity, publication path, NAS/Jellyfin path, and alignment policy are
  unchanged. No title/cue/text-specific branch was added.

### Offline verification

- Exact reason coverage: session mismatch, SHA mismatch, cue-count/missing
  cue, duplicate cue, first-cue/order mismatch, malformed `ko`, malformed
  `repaired_ja`, schema, and JSON parse cases all pass.
- Hermes timeout simulation passes with start/end/elapsed/timeout/result
  markers; PASS and FAIL result markers also pass.
- Existing stateful parts/controller/policy/live-runner/retry/timeout,
  Stage12 batch/inventory/rollout, and fixed-128 benchmark regression smokes
  all pass. `py_compile` passes.
- CP7K live/write counters: `LIVE_HERMES_CALLS=0`, `NAS_WRITES=0`,
  `JELLYFIN_CALLS=0`, `ROLLOUT_DB_WRITES=0`.

### CP7K changed files

- `teddy_discovery_stateful_parts.py`
- `teddy_discovery_stateful_live_runner.py`
- `teddy_discovery_stateful_parts_smoke.py`
- `teddy_discovery_stateful_live_runner_retry_smoke.py`
- `teddy_discovery_stateful_live_runner_timeout_smoke.py`
- `docs/handoff/missav-dlp-web/CURRENT_HANDOFF.md`

No commit or push was attempted.

## CP7L / CP7M — Source-Aware Generic Runaway Validation

`STAGE12_CP7L_SOURCE_AWARE_RUNAWAY_FORENSIC`

CP7L's exact diagnosis is a generic validator-boundary false positive, not a
title-specific translation rule or a fixed-128 failure. The existing KO guard
correctly rejects a whole-string short-unit runaway on its own, but it had no
access to the authoritative Japanese source for the corresponding output cue.

- Case A: the source had 13 periodic repetitions while KO had 72 repetitions.
  The KO output was amplified relative to source, so rejection remains the
  correct fail-closed result.
- Case B: the source had 74 complete periodic repetitions plus a trailing
  partial unit while KO had 40 repetitions. The KO was source-grounded and
  shorter, so the existing source-blind detector falsely rejected it.
- No title, cue, or text-specific production branch is justified by this
  finding.

`STAGE12_CP7M_GENERIC_SOURCE_AWARE_RUNAWAY_CANDIDATE`

CP7M implements the conservative candidate exception at the stateful part
validator boundary:

- The existing `has_runaway_repetition()` call and thresholds remain the first
  gate. Source evidence is evaluated only when that existing KO detector fires.
- The exact source cue is retained from the already-authorized package/input
  flow. Existing precedence is reused: `external_ja` when present, otherwise
  `stt_ja`; context and EN are not source authority.
- Source evidence uses whitespace-normalized text and accepts only a 1–4
  character unit with at least 16 complete repetitions in the exact form
  `unit * N + optional prefix(unit)`. A middle mismatch produces no evidence.
- The exception is allowed only when source evidence exists and the complete KO
  repetition count reported by the existing detector is less than or equal to
  the source complete repetition count. Source unavailable, ambiguous, or
  malformed remains `INVALID_KO`.
- The part/result JSON envelopes, cue identity/order/SHA/session checks,
  repaired-JA validation, retry count, and timeout remain unchanged.

The production default remains `STATEFUL_PART_BATCH_SIZE=16`. Fixed-128 general
promotion is still **NOT APPROVED**; CP7M does not promote fixed-128 globally.
The generic offline matrix passed: source 13 / KO 72 rejected; source 74 plus
partial / KO 40 accepted; non-periodic, larger-KO, absent-source, and malformed
source cases rejected; equal and smaller KO counts accepted. The existing
runaway/retry/timeout/policy smokes and `py_compile` also passed.

CP7M counters were all zero: `LIVE_HERMES_CALLS=0`, `NAS_WRITES=0`,
`JELLYFIN_CALLS=0`, `ROLLOUT_DB_WRITES=0`. No commit or push was attempted.

### Next checkpoint (one)

**CT108 read-only remote artifact forensics:** use the new diagnostic fields
and markers when reading CT120 task/session evidence to resolve the retained
CP7I DVAJ-754 inner validator reason and DVDES-795 post-timeout artifact state.
No retry, re-execution, fallback, timeout change, validator change, or
publication is authorized by this checkpoint.

## Stage12 CP7N Fresh Fixed-128 Bounded Rollout — COMPLETE / 1 of 3 PUBLISHED

`STAGE12_CP7N_FIXED128_FRESH_BOUNDED_ROLLOUT_COMPLETE`

CP7N is **CLOSED / COMPLETE**. It ran one fresh deterministic three-title
fixed-128 batch in `dvd_id` ascending order. The finalized live summary is:

- `STAGE12_CP7N_LIVE=COMPLETE`
- `selected=3`
- `published=1`
- `failed_retryable=2`
- `failed_terminal=0`
- `skipped=0`
- `unresolved=0`

The selector remained the generic bounded selector:
`PENDING AND ELIGIBLE_NEEDS_KO AND existing_ko=ABSENT`, ordered by `dvd_id`
ascending. No title-specific selection or production branch was used.

### CP7N per-title outcomes

- `DVDMS-117`: Stage11 `PASS`; route `ASR_ONLY`; baseline cue count `491`;
  fixed-128 stateful part count `4`; NAS publication `PASS`; Jellyfin
  recognition `PASS`; final state `PUBLISHED`; destination
  `DVDMS/DVDMS-117/DVDMS-117.ko.srt`.
- `EBWH-350`: baseline cue count `943`; fixed-128 planned part count `8`;
  parts `1–4` promoted successfully; part `5` Hermes invocation timed out at
  the unchanged `600` seconds; Stage11 `FAIL`; NAS publication `NOT_RUN`;
  Jellyfin recognition `NOT_RUN`; final state `FAILED_RETRYABLE`.
- `EBWH-353`: baseline cue count `1468`; fixed-128 planned part count `12`;
  part `1` Hermes invocation timed out at the unchanged `600` seconds;
  Stage11 `FAIL`; NAS publication `NOT_RUN`; Jellyfin recognition `NOT_RUN`;
  final state `FAILED_RETRYABLE`.

Title-level isolation held: the two timeout failures did not stop the
successful title, and failed titles were not published or sent to Jellyfin.
No failed title was retried during closure.

### CP7N policy and diagnostic decision

- Fixed-128 policy: `stage11-stateful-cue128-v1`.
- Production global default: `16`, unchanged.
- Hermes timeout: `600` seconds, unchanged.
- Stateful retry count: unchanged; no timeout-triggered blind retry.
- Validator structural rules: unchanged; validators were not weakened.
- CP7K generic stateful failure diagnostics: active and retained.
- CP7M source-aware repeated-cue validator: active and unchanged.
- Fixed-128 general production promotion: **NOT APPROVED**.
- Failed titles must not be blindly retried.

CP7N provides fresh evidence that fixed-128 is not yet reliable enough for
general production promotion. The two timeout outcomes do not establish that
`128` itself is conclusively the root cause of both failures; that causal
claim remains unproven.

This closure update changed only this canonical handoff. It performed no new
Hermes, ASR, NAS, Jellyfin, or rollout-state operation.

### CP7N next checkpoint (one)

Make a separately authorized fixed-128 reliability decision from the complete
CP7N evidence; until then retain the 16-cue production default and do not
retry the failed titles or change timeout, retry, or validator policy.

## Stage12 CP7O Fresh Fixed-64 Bounded Rollout Preparation — PREFLIGHT / NETWORK DEFERRED

`STAGE12_CP7O_FIXED64_BOUNDED_ROLLOUT_PREPARATION`

CP7O prepared an isolated generic fixed-64 production-path candidate for a
fresh bounded three-title rollout.  This checkpoint is preparation only:
there was no Hermes call, ASR call, NAS write, Jellyfin write/call, or rollout
DB write, and no existing `FAILED_RETRYABLE` title was retried.

### Repository and policy contract

- At CP7O start, before the candidate registration edits, the repository was
  clean at HEAD `bb3392aec2af0948e95710f3813a47f30346f141` on branch
  `teddy-subtitle-stage11`.
- The existing isolated benchmark fixed-64 identity remains
  `benchmark-stateful-cue64-v1`.  CP7O registers the opt-in production-path
  candidate identity `stage11-stateful-cue64-v1` through the existing native
  policy mechanism; its maximum is `64` cues per part.
- Production global default remains `stage11-stateful-cue16-v1` / `16` cues.
  Fixed-64 general promotion is **NOT APPROVED**.
- Hermes timeout remains `600` seconds; bounded retry count remains `2`.
  Validators, CP7K diagnostics, CP7M source-aware validation, and Stage11
  controller behavior remain unchanged.

### Generic deterministic selection

The selector is exactly:

`PENDING AND eligibility = ELIGIBLE_NEEDS_KO AND existing_ko = ABSENT ORDER BY dvd_id ASC LIMIT 3`

The read-only rollout DB contained `152 PENDING`, `7 FAILED_RETRYABLE`,
`13 PUBLISHED`, `1 UNRESOLVED`, and no `RUNNING` / `GENERATED` rows.  The
fresh selected titles were:

| dvd_id | status | eligibility | existing_ko |
| --- | --- | --- | --- |
| `EBWH-354` | `PENDING` | `ELIGIBLE_NEEDS_KO` | `ABSENT` |
| `EKDV-826` | `PENDING` | `ELIGIBLE_NEEDS_KO` | `ABSENT` |
| `EROFV-366` | `PENDING` | `ELIGIBLE_NEEDS_KO` | `ABSENT` |

No title ID is present in the selector or production logic.

### Per-title read-only preflight

All three selected titles had no reusable baseline in either the isolated
CP7O artifact root or the canonical reusable baseline root.  Therefore no
baseline cue count or deterministic fixed-64 part count was available without
an ASR call; every expected part count is `N/A` at this checkpoint.

| dvd_id | reusable baseline | baseline cues | expected fixed-64 parts | exact publication destination | current NAS canonical KO |
| --- | --- | ---: | ---: | --- | --- |
| `EBWH-354` | `ABSENT` | `N/A` | `N/A` | `EBWH/EBWH-354/EBWH-354.ko.srt` | `DEFERRED_SANDBOX` — exact path not read |
| `EKDV-826` | `ABSENT` | `N/A` | `N/A` | `EKDV/EKDV-826/EKDV-826.ko.srt` | `DEFERRED_SANDBOX` — exact path not read |
| `EROFV-366` | `ABSENT` | `N/A` | `N/A` | `EROFV/EROFV-366/EROFV-366.ko.srt` | `DEFERRED_SANDBOX` — exact path not read |

The exact Jellyfin-visible destinations are respectively
`/media/adult/EBWH/EBWH-354/EBWH-354.ko.srt`,
`/media/adult/EKDV/EKDV-826/EKDV-826.ko.srt`, and
`/media/adult/EROFV/EROFV-366/EROFV-366.ko.srt`.

### Safety and connectivity checks

- Serial title isolation: `PASS` through the existing Stage12 batch runner.
- Atomic no-overwrite publication: `PASS` through the existing publisher.
- Exact NAS recheck immediately before publication: `PASS` by source-order
  inspection of the existing Stage12 batch runner.
- Jellyfin item-specific recognition: `PASS` by source-order inspection of
  the exact item/playback/refresh contract.
- CP7K diagnostics: `ACTIVE`.
- CP7M source-aware validator: `ACTIVE`.
- CT120 Hermes, VM122 ASR, NAS, and Jellyfin TCP probes:
  `DEFERRED_SANDBOX` because this execution environment disables network
  access.  The exact selected NAS subtitle inventory was consequently not
  executed, and canonical KO presence is not claimed absent.

### Isolated runner and offline result

- Runner: `/tmp/stage12-cp7o-fixed64-rollout-runner.py`.
- Live authorization is explicitly gated by
  `CP7O_ALLOW_LIVE=CP7O_AUTHORIZED`; the marker was not set and live mode
  negative smoke returned `2` with zero calls/writes.
- `py_compile`: `PASS`.
- Existing relevant stateful/controller/Stage12/benchmark offline smokes:
  `PASS`.
- CP7O preflight: `INCOMPLETE_NETWORK_DEFERRED` / **FAIL CLOSED** at the
  required exact-NAS connectivity gate.
- `READY_FOR_AUTHORIZATION`: **NO**.  Exact NAS revalidation and all four
  connectivity checks must pass in an authorized networked environment before
  any live decision.
- Counters: `LIVE_HERMES_CALLS=0`, `ASR_CALLS=0`, `NAS_WRITES=0`,
  `JELLYFIN_CALLS=0`, `ROLLOUT_DB_WRITES=0`.

### CP7O changed files and blocker

- `teddy_discovery_stateful_policy.py`: opt-in fixed-64 production policy
  registration only.
- `teddy_discovery_stateful_policy_smoke.py`: fixed-64 policy/partition smoke
  coverage.
- This handoff.
- The deployment smoke could not run in the available environment because
  `numpy` is not installed; this is separate from the CP7O preflight boundary
  and caused no production operation.
- No live execution is authorized by CP7O.

## Stage12 CP7O Fresh Fixed-64 Bounded Live Rollout — COMPLETE / 3 of 3 PUBLISHED

The preceding CP7O section records the earlier preparation and fail-closed
preflight boundary.  The subsequently authorized fresh bounded live rollout
completed with the following finalized evidence:

`STAGE12_CP7O_LIVE=COMPLETE`

| selected | published | failed_retryable | failed_terminal | skipped | unresolved |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 3 | 3 | 0 | 0 | 0 | 0 |

### CP7O per-title outcomes

#### EBWH-354

- Fixed-64 stateful run completed `5/5` parts.
- Stage11: `PASS`.
- Route: `ASR_ONLY`.
- NAS publication: `PASS`.
- Jellyfin recognition: `PASS`.
- Final state: `PUBLISHED`.
- Destination: `EBWH/EBWH-354/EBWH-354.ko.srt`.

#### EKDV-826

- Cue count: `357`.
- Fixed-64 part count: `6`.
- All `6/6` parts `PASS` / promoted.
- Stage11: `PASS`.
- Route: `ASR_ONLY`.
- NAS publication: `PASS`.
- Jellyfin recognition: `PASS`.
- Final state: `PUBLISHED`.
- Destination: `EKDV/EKDV-826/EKDV-826.ko.srt`.

#### EROFV-366

- Cue count: `231`.
- Fixed-64 part count: `4`.
- All `4/4` parts `PASS` / promoted.
- Stage11: `PASS`.
- Route: `ASR_ONLY`.
- NAS publication: `PASS`.
- Jellyfin recognition: `PASS`.
- Final state: `PUBLISHED`.
- Destination: `EROFV/EROFV-366/EROFV-366.ko.srt`.

### CP7O decision state

- Fixed-64 has now passed a fresh three-title production-path rollout `3/3`.
- The prior fixed-128 fresh rollout passed only `1/3`, with two
  `600`-second Hermes timeouts.
- This is strong evidence in favor of fixed-64 over fixed-128 for production
  use, but it does not establish that fixed-64 is universally faster or
  guaranteed timeout-free.
- The production global default remains fixed-16 **FOR NOW**.
- The fixed-64 promotion decision is the next checkpoint.
- Do not retry the prior failed titles yet.
- Hermes timeout remains `600` seconds.
- Bounded retry count remains `2`.
- CP7K diagnostics and the CP7M validator remain active and unchanged.

## Stage12 CP7P / CP7Q Fixed-64 Production Default Promotion — CP7P APPROVED / CP7Q OFFLINE IMPLEMENTATION INCOMPLETE

CP7P approved promotion of the fixed-64 policy based on the closed CP7B
benchmark and the fresh CP7O production-path result.  The decision remains
operational and evidence-based; it does not claim that fixed-64 is
universally faster or that fixed-128 is conclusively the sole cause of every
timeout.

`PROMOTION_RECOMMENDATION=APPROVE_FIXED64_DEFAULT`

CP7Q implements the production-default change as follows:

- `DEFAULT_STATEFUL_SEMANTIC_POLICY` is now
  `stage11-stateful-cue64-v1`.
- The active default `STATEFUL_PART_BATCH_SIZE`, policy ID, planner defaults,
  controller defaults, live-runner defaults, and CLI semantic-policy default
  therefore use `64` cues per part.
- `stage11-stateful-cue16-v1`, `stage11-stateful-cue64-v1`, and
  `stage11-stateful-cue128-v1` remain registered and selectable.
- `benchmark-stateful-cue64-v1` remains a separate benchmark namespace and
  policy ID; it was not repurposed as the production policy.
- New/default fixed-64 packages are bound to
  `::stage11-policy=stage11-stateful-cue64-v1`.  Explicit legacy-16 binding
  remains a deliberate no-op so valid historical unbound 16-cue package,
  session, and resume identities remain usable.
- An unbound legacy package cannot be planned as fixed-64.  Fixed-64,
  fixed-128, and explicit legacy-16 state are rejected when their policy,
  session, input, or part identity is mismatched.  Incompatible partial or
  ambiguous resume state fails closed.  The UUID/session derivation algorithm
  itself is unchanged.
- Validated existing completed/PUBLISHED artifacts may still be reused by the
  default fixed-64 path or explicit legacy-16 path through the existing
  source/artifact validation contract.  They are not rewritten merely because
  the default changed.  The fixed-128 candidate remains explicit and is not
  the default.

The following remain frozen and unchanged: the `600`-second Hermes timeout,
model attempt count `2`, CP7K diagnostics, the CP7M source-aware validator,
the `4096` cue structural limit, the `16 MiB` resource bound, deterministic
timestamps and identity derivation, atomic no-overwrite publication, NAS and
Jellyfin contracts, Stage12 selection/state transitions, and the absence of
adaptive or title/cue/text-specific policy branching.

CP7Q performed offline-only implementation and regression work.  No live
activation, production rollout, failed-title retry, Stage12 state mutation,
Hermes/ASR call, NAS publication, Jellyfin refresh, or rollout-DB write was
performed.  The available offline regressions passed; the Stage11 live-adapter
and deployment smokes could not start because the Codex environment lacks
`numpy`.  They must be run on CT108 before this implementation is considered
fully validated.

The next checkpoint is CT108 offline regression completion, followed only by
a separately authorized production canary/activation.  This CP7Q checkpoint
does not authorize production activation.

## Stage12 CP7T / CP7U — Pre-Hermes Pathological Repetition Audit and Model-Input Normalization — CP7T PASS / CP7U OFFLINE IMPLEMENTED / CT108 PENDING

`STAGE12_CP7T_PRE_HERMES_REPETITION_AUDIT_PASS`

`STAGE12_CP7U_GENERIC_MODEL_INPUT_NORMALIZATION_OFFLINE_IMPLEMENTED`

`STAGE12_CP7U_READY_FOR_CT108_REGRESSION`

CP7T audited the existing source path on branch `teddy-subtitle-stage11` at
the expected HEAD `2264f8f0d1202d96ce0a4eb2bcf5c6eb510f9964`.  No production
call, failed-title retry, rollout-DB write, NAS/Jellyfin operation, Hermes
state mutation, or ASR-artifact mutation was performed.

### CP7T forensic audit

The existing filters and their contracts are:

- `teddy_discovery_nonlexical.py:classify_nonlexical()` calls the
  classification-only `_analysis_core()`.  NFKC, outer whitespace, and the
  narrow surrounding-punctuation view are not returned to the caller.  Only
  a pure repeated vowel-like Japanese kana run is `OMIT`; all other text is
  `KEEP` and its source text is unchanged.
- `teddy_discovery_asr_source_quality.py:_repeated_short_unit()` and
  `classify_asr_result_source_quality()` observe whole-string structural
  repetition, consecutive segment runs, and document recurrence.  They do
  not rewrite text.  The existing nonlexical `OMIT` remains the only hard
  omission; other source-quality findings remain bounded evidence/action
  decisions.
- `teddy_discovery_stateful_prepare.py:prepare_stateful_package()` applies
  the existing deterministic `OMIT` decisions before retained package
  construction.  Omitted cues stay omitted and retained cues are copied
  unchanged.  `build_stateful_asr_package()` and
  `prepare_stateful_asr_package()` validate exact ASR source text and do not
  normalize it.
- `teddy_discovery_subtitle_v2_pipeline.py:_build_local_plan()`,
  `build_asr_only_cue_sequence()`, and `_build_hybrid_cues()` construct raw
  external/ASR evidence and preserve cue order/context.  The existing
  targeted-Hybrid `has_runaway_repetition()` check can omit that targeted
  evidence from semantic enrichment, but it does not rewrite the retained
  authoritative cue.
- `teddy_discovery_stateful_parts.py:has_runaway_repetition()` /
  `periodic_repetition_evidence()` are existing post-Hermes validator
  evidence functions.  They inspect only a whole-string exact periodic form
  after whitespace normalization; they do not delete or normalize input.
- `teddy_discovery_stateful_translator.py:serialize_stateful_package()` and
  the prior `write_stateful_input()` path previously serialized retained
  source as-is.  They were not pre-Hermes source filters.
- ASR transcript canonicalization remains limited to line-ending/outer-string
  handling in the existing ASR path; it is not a repetition filter.  CLEAN,
  quality-review, publication, timestamp, and resource-limit paths remain
  validators/materializers rather than source normalization paths.

The CP7R cue escaped because `あ` followed by `ー` repeated 444 times is not a
whole-string periodic repetition: the first codepoint differs from the long
suffix run, and the full 445-codepoint string is not an exact 1–4-codepoint
unit repeated an integral number of times.  Therefore
`has_runaway_repetition=False`, `periodic_repetition_evidence=None`, and the
existing ASR short-unit observer found no whole-string match.  The mixed
`あ`/`ー` text also is not the pure vowel-like-kana shape recognized by
`classify_nonlexical()`, and `ー` is outside that classifier's vowel set.  It
was consequently retained as `KEEP` and reached Hermes unchanged.

Prior generic evidence includes the CP6F4 `AVSA-455` repeated short-unit ASR
hallucination, CP7L/CP7M source-grounded periodic source evidence, and
`HSODA-104` retained-KEEP repeated dialogue evidence.  Together with the
CP7R `EROFV-387` observation, this supports a generic retained-cue
model-input bound; it does not support a title/cue/text-specific rule or
whole-cue deletion.

### CP7U implementation contract

The new pure module `teddy_discovery_model_input_normalization.py` exposes
`normalize_model_input_text(raw_text)` and immutable projection/metadata
values.  It is deterministic, idempotent, does not mutate its input, does
not strip whitespace/punctuation or apply NFKC, never deletes a cue, and
leaves ambiguous combining/format/emoji-grapheme structures unchanged.

The evidence-based bounds are fixed at pathological codepoint/run floor `64`,
short-unit maximum `4`, and minimum `16` complete periodic repetitions.  The
shortest safe unit wins.  A qualifying single-codepoint run is replaced by
two representative codepoints; a qualifying distinct unit of length 2–4 is
replaced by two representative units, with an existing trailing partial unit
prefix preserved.  Punctuation/symbol-only units additionally require a
64-codepoint span.  Thus `あ` + `ー` × 444 becomes `あーー`, `あ` × 400 is
bounded when retained, internal extreme short-unit runs are bounded, and
ordinary `すごーーい`, short repetition, and sub-bound punctuation remain
unchanged.

The representation boundary is explicit:

- `StatefulSubtitlePackage` and its `external_ja`, `stt_ja`, and any retained
  raw evidence remain authoritative and exact.  The stateful staging sidecar
  is `stage11-authoritative-input.json`.
- `stage11-semantic-input.json` is the deterministic model-input projection
  produced after existing source filtering and source selection.  It keeps
  the same cue IDs, order, and package identity metadata; only pathological
  text spans may differ.  Stateful first-pass staging validates and passes
  both paths, and the runner requires the raw sidecar whenever the model-input
  identity is bound.
- External-JA precedence remains `external_ja` when present, otherwise
  `stt_ja`; this precedence and the raw values are not rewritten.  `repaired_ja`
  is an output/provenance field, not a first-pass Hermes input, and remains
  exact under the unchanged validator/review paths.
- One-shot semantic calls project at
  `teddy_discovery_subtitle_v2_pipeline.py:_call_semantic_boundary()` and the
  Hermes transport/batching boundaries defensively project before prompt or
  batch construction.  Stateful projection is centralized in
  `build_stateful_model_input_package()` / `serialize_stateful_model_input()`
  and staged by the live adapter/deployment path.

The model-input identity is
`stage11-model-input=repeat-v1`, bound in the existing generation-key
mechanism before the semantic-policy suffix.  Normalized model bytes are the
stateful `input_sha256`; the existing UUID5/session derivation algorithm is
unchanged, while the bound generation key creates a distinct session for the
new transformation.  Old unnormalized semantic input is rejected by the
deterministic package projection check; old partial state cannot be read as a
new normalized session.  Existing raw ASR/external evidence can still be
reused when its existing provenance validation matches.  The completed
controller report/publication schema is unchanged, while completion reuse now
requires the report's translation identity to match the CP7U raw package,
normalized model package, and semantic result staging; missing or mismatched
semantic staging fails closed.  The new stateful semantic part/session
boundary is therefore isolated without changing the UUID algorithm.

CP7M remains source-aware over `StatefulPartPlan.source_cues`, which now
continues to hold the raw authoritative package while the plan hash is over
the model-input bytes.  The CP7M predicates and thresholds were not weakened.
If normalized `あーー` still produced `아` × 474, the raw
`あ` + `ー` × 444 remains available to the unchanged CP7M/`INVALID_KO`
decision, so normalization cannot create a false source-grounded exception.

Fixed-64 remains the production default.  Timeout `600`, attempt count `2`,
CP7K diagnostics, CP7M/`INVALID_KO`, structural/resource limits, timestamps,
publication, Stage12 state transitions, and the absence of adaptive policy
remain unchanged.  CP7S retry-feedback work is deferred and is not included
in CP7U.

### CP7U changed files

- `teddy_discovery_model_input_normalization.py`
- `teddy_discovery_model_input_normalization_smoke.py`
- `teddy_discovery_hermes_v2_batching.py`
- `teddy_discovery_hermes_v2_transport.py`
- `teddy_discovery_stage11_controller.py`
- `teddy_discovery_stage11_controller_smoke.py`
- `teddy_discovery_stage11_deployment.py`
- `teddy_discovery_stage11_live_adapters.py`
- `teddy_discovery_stateful_live_runner.py`
- `teddy_discovery_stateful_parts.py`
- `teddy_discovery_stateful_parts_smoke.py`
- `teddy_discovery_stateful_translator.py`
- `teddy_discovery_subtitle_v2_pipeline.py`
- `docs/handoff/missav-dlp-web/CURRENT_HANDOFF.md`

### CP7U offline verification

- New normalization smoke: `24/24` checks passed, including mixed suffix,
  pure-nonlexical `OMIT` preservation, normal emphasis, internal periodic
  runs, idempotence, ambiguous-Unicode fail-closed behavior, one-shot/batch
  Hermes projection, raw/model separation, raw CP7M rejection/grounding,
  identity isolation, fixed-16/fixed-64/fixed-128 policy behavior, adapter
  staging, and no title/cue/text-specific branches.
- `34` relevant offline smoke programs passed.  Counted suites include
  stateful ASR `32`, hybrid `49`, ASR-SRT `6`, parts `45`, stateful
  controller `26`, policy `17`, live runner `16`, thin Stage11 controller
  `46`, quality review `134`, quality-review CLEAN `32`, context `41`,
  proximity `66`, review runner `86`, direct ASR review runner `33`, fixed-64
  benchmark `45`, and fixed-128 benchmark `54`; the CP7U smoke is `24`.
  The remaining passed smokes reported PASS without an assertion counter.
- `py_compile` passed for all `13` changed Python files and `git diff --check`
  passed.
- `teddy_discovery_stage11_live_adapters_smoke.py` and
  `teddy_discovery_stage11_deployment_smoke.py` remain environment-blocked
  before test execution by `ModuleNotFoundError: No module named 'numpy'`.
  No installation was attempted; CT108 must run these regressions.
- Offline production counters were zero: production calls/writes `0`,
  including Hermes, ASR, rollout DB, NAS, and Jellyfin.

No commit or push was attempted.  CP7U is ready for CT108 offline regression;
it does not authorize production activation or any failed-title retry.

### CP7U CT108 fixture-only regression correction

`STAGE12_CP7U_CT108_FIXTURE_DOUBLE_WRITE_CORRECTED`

The CT108 failure was a test-fixture ownership mismatch, not a production
double write or stale staging directory.  The live adapter wrote the raw and
model first-pass artifacts, then the shared controller `FakeRuntime` tried to
write the same raw/model/result paths again from inside the native callback.
The fixture now has an explicit staging mode: direct controller tests retain
their one-time fixture staging, while live-adapter and deployment wrappers use
a return-only fake and own result installation themselves.  Production
writers, `_atomic_private_write`, CP7U normalization, CP7M, CP7K, and all
frozen policy/timeout/retry behavior are unchanged.

Post-correction offline verification:

- Stage11 controller smoke: `46/46`.
- Model-input normalization smoke: `24/24`.
- Stateful parts: `45/45`; stateful ASR: `32/32`; stateful ASR-SRT: `6/6`;
  stateful Hybrid: `49/49`; stateful dynamic controller: `26/26`;
  stateful live runner: `16/16`; retry and timeout contracts passed;
  stateful policy: `17/17`.
- Translator, ASR source-quality, stateful prepare, subtitle-v2 pipeline,
  Hermes batching, and Hermes transport smokes passed their existing PASS
  contracts.
- `py_compile` passed for `13` changed Python files and `git diff --check`
  passed.  The live-adapter and deployment smokes remain blocked before test
  execution by `ModuleNotFoundError: No module named 'numpy'`; no dependency
  installation was attempted.
- No production call/write, failed-title retry, rollout-DB, NAS, Jellyfin,
  Hermes-state, or ASR-artifact operation was performed.

`READY_FOR_CT108_REGRESSION=YES`

## Future roadmap after subtitle pipeline closure — USER-APPROVED / NOT AUTHORIZATION

The following future roadmap requirements came from the user and are approved
as the intended sequence.  They are recorded for handoff purposes only and are
**not authorization to implement them yet**.  No current CP7O execution state,
Stage12 conclusion, timeout, retry policy, rollout state, or production
operation is changed by this roadmap.

The order below is intentional and must be preserved.

### 1. Finish all subtitle-related stages first

- Complete the current fixed-64 evaluation and all remaining subtitle
  rollout, quality, and operational work.
- Decide the final production semantic cue policy only after the evidence is
  sufficient.
- Resolve the remaining subtitle-stage operational policy as needed.
- Do not begin the file-manager stage until the subtitle pipeline is formally
  closed.
- Avoid switching back and forth between subtitle work and file-management
  work.

### 2. Jellyfin DVD-ID / product-code search improvement

#### Goal

Jellyfin currently allows practical title search, but product-code/DVD-ID
search is inadequate.  Make the canonical DVD-ID/product code searchable in
Jellyfin, preserve the normal display title where practical, and store the
canonical DVD-ID separately as a stable identifier as well.

#### Required investigation before implementation

- Do **not** freeze the exact Jellyfin metadata field yet.
- Before implementation, perform a read-only investigation of the current
  metadata, NFO, and Jellyfin search behavior in this deployment.
- Determine which searchable metadata field should carry the DVD-ID without
  unnecessarily polluting the visible display title.
- Also retain a canonical identifier field/provider ID/unique ID if
  appropriate.
- The final field mapping must be evidence-based from the actual Jellyfin
  behavior in this deployment.

### 3. Next major stage: NAS Library File Manager

#### Goal

Convert the existing File Management tab from a transient download-file view
into a persistent NAS JAV library manager.

#### Source of truth and scope

- NAS library root: `/volume1/video/video2/JAV`
- The UI must list all managed works/files that actually exist in the NAS JAV
  library, including items that disappeared from the old list after download
  completion or move.

#### UI requirements

- Use a discovery-style collapsible/expandable list.
- Each work/title appears as a row/card that can be expanded.
- Expanded details show screenshots and metadata.
- Video preview/playback preview is explicitly **not required** in this
  file-management view.
- Korean subtitle status is important and must be shown clearly.
- Japanese subtitle presence does not need to be shown.

#### Search, filter, and sort requirements

- Search by DVD-ID/product code.
- Search by title.
- Filter for Korean subtitle present or absent.
- Sorting must support at least:
  - download/addition date;
  - Korean subtitle presence;
  - release date;
  - DVD-ID/product code;
  - title.
- Additional useful library-management sorts may be added later if they fit
  the existing design cleanly.

#### Delete behavior

- Provide a delete action for a work/title.
- Deletion must affect the actual NAS files.
- This is destructive and must be implemented fail-closed.
- Require clear user confirmation before deletion.
- Validate that every deletion target is inside the canonical NAS JAV library
  root.
- Never allow path traversal, unexpected paths, symlink escapes, or broad
  recursive deletion.
- Prefer work/title-scoped deletion of the exact known managed files.
- After deletion, refresh or reconcile Jellyfin as needed.
- Investigate Synology recycle-bin/trash behavior before deciding whether
  permanent deletion or recycle-bin semantics should be used.

#### Architecture preference

- Do not perform a broad recursive NAS scan on every page load.
- Prefer a durable inventory/cache/database model with bounded
  reconciliation.
- Reuse existing Discovery/holding/metadata knowledge where possible.
- Keep NAS reads bounded and exact.
- The native-first/minimal-change policy remains in force.

### 4. Stage transition rule

- Subtitle work must be formally **CLOSED** before starting the
  Jellyfin-search/file-manager implementation stage.
- When subtitle closure is reached, create the next implementation plan from
  this canonical handoff rather than relying on chat memory.

## Stage12 CP7W / CP7X — EROFV-387 Normalized Recovery Attempt and Orphan-State Repair — CP7X CLOSED / FRESH PREFLIGHT REQUIRED

STAGE12_CP7W_FIRST_LIVE_ATTEMPT_RECORDED

STAGE12_CP7X_ORPHAN_STATE_REPAIR_RECORDED

CP7W's first live attempt targeted EROFV-387 while its rollout state was
FAILED_RETRYABLE.  Event 246 claimed the title through
FAILED_RETRYABLE -> RUNNING with normalization
stage11-model-input=repeat-v1 and new session
f1381da2-f514-54bf-8769-aff34dd71d48.  The temporary recovery runner then
failed before Stage11 execution because it attempted to import _artifact from
teddy_discovery_stage12_rollout, where that symbol does not exist.

Forensic review confirmed that no CP7W process remained active, no Stage11
semantic execution completed, no NAS publication or Jellyfin refresh
occurred, and artifact/report fields remained NULL.  Event 246 therefore
left an orphan RUNNING state.  The corrected temporary runner obtains
_artifact from teddy_discovery_stage12_batch; it remains outside the
repository and no tracked production-source modification was made.

CP7X repaired the orphan through the existing
Stage12RolloutStateStore.transition(...) contract with
expected_from=RUNNING, using reason STAGE12_TITLE_FAILURE.  The direct
CT108 exact NAS canonical KO check was ABSENT.  The repair transitioned
RUNNING -> FAILED_RETRYABLE, appended event 247, and advanced
transition_sequence from 4 to 5.  Its provenance operation was
STAGE12_CP7W_ORPHAN_STATE_REPAIR with retry_performed=false, the CP7W batch
membership, normalization version, new session, and the temporary-runner
ImportError context.

Prior events 23/244/245/246 remain unchanged; artifact/report fields remain
NULL; no other rollout title changed; and the repair performed zero Hermes,
ASR, NAS, or Jellyfin calls/writes.  EROFV-387 is safely back in
FAILED_RETRYABLE.  Any new recovery attempt requires a fresh CP7W preflight,
must use the normalized identity, must not reuse the failed old semantic
session, and must retain fixed-64 as the default.  CP7U normalization remains
active.

## Stage12 CP7W — EROFV-387 Normalized Recovery Completed

STAGE12_CP7W_CLOSED

The authorized normalized recovery of EROFV-387 completed successfully.
The raw authoritative pathological cue remained exactly `あ` followed by
`ー` repeated 444 times, while the Hermes model-input projection was the
bounded representative `あーー`.  The model-input normalization identity was
`stage11-model-input=repeat-v1`.  All seven semantic parts completed; part 6,
which had failed validation in the prior run, passed validation and was
promoted.

The recovery used semantic policy `stage11-stateful-cue64-v1` with the old
session `134bcb2f-2e84-5802-b7c8-3fabaeefade4` kept separate from the new
session `f1381da2-f514-54bf-8769-aff34dd71d48`.  Stage11 passed and the
rollout reached `PUBLISHED`.

Confirmed recovery identities:

- `FINAL_RESULT_SHA256`: `84345f2cb6a8aea7db3047ecd0d4582eceb3e1159502506c9f8efff91cb46e44`
- `FINAL_CUE_COUNT`: `386`
- `CLEAN_SHA256`: `161aade5dc4f2562ed36dacc32b9b55d5825335730cfdaf96b866d1121a29524`
- NAS publication: `PASS`
- rollout final state: `PUBLISHED`

Structured Jellyfin recognition passed with `external_visible=true`,
`subtitle_language=kor`, subtitle path
`/media/adult/EROFV/EROFV-387/EROFV-387.ko.srt`, and item ID
`4feab2175c2ae0bf72645afc9c37ad74`.  A top-level
`JELLYFIN_RECOGNITION=UNKNOWN` summary field is a reporting discrepancy only;
the structured recognition result is authoritative and successful.

### CP7W runner incidents and resolution

1. The first temporary runner used an invalid `_artifact` import, failed before
   Stage11 execution, and left an orphan state that was repaired through the
   existing Stage12 transition contract.
2. The second temporary runner found that the newly configured CT120 remote
   task root was absent.  `ensure_task` expects its configured parent root to
   already exist, so it failed before session creation and Hermes execution.
3. The hardened r3 temporary runner provisioned and verified the exact CT120
   remote task root before the rollout claim, preventing another
   provisioning-caused orphan `RUNNING` state.
4. The r3 live recovery then completed successfully.

The corrected r3 runner remains temporary and outside the repository.  No
tracked production-source modification was made for these runner fixes.

### CP7W interpretation

CP7U pathological-repetition normalization now has one successful production
recovery confirmation on EROFV-387.  This is evidence for the generic
normalization path, not evidence that every `FAILED_RETRYABLE` title is
repetition-related.  Fixed-64 remains the production default; fixed-128
remains explicit and non-default.  Timeout and retry settings are unchanged.
The CP7S structured retry-feedback improvement remains deferred.

STAGE12_CP7W_FINAL_RESULT=PASS

## Stage12 R5B Recovery and DVDES-795 Missing-Pending Fix — COMPLETE

`STAGE12_R5B_RECOVERY_BATCH_COMPLETE`

The R5B recovery batch completed. `AVSA-456`, `DVAJ-754`, and `EBWH-353`
were recovered and published; previously recovered `AVSA-455` remains
`PUBLISHED`. Remaining `FAILED_RETRYABLE` titles are `DASS-884`,
`DVDES-795`, and `EBWH-350`. `DASS-884` timed out at Hermes part `28/30`,
and `EBWH-350` at part `10/15`; both retained `timeout=600`.

`DVDES-795` Hermes part 5 returned `PASS`, but the expected remote
`semantic-part-0005.pending.json` was absent. `_read_remote_regular_file()`
raised generic `StatefulLiveRunnerError`; Stage12 did not classify it as a
title exception and wrapped it in `Stage12BatchSystemicError`.

The narrow fix adds `StatefulLiveRunnerPendingArtifactError`. Only a remote
`FileNotFoundError` for the pending artifact maps to this subclass. Generic
`StatefulLiveRunnerError` remains systemic, and Stage12 treats only this new
pending-artifact exception as title-level retryable. Timeout behavior,
fixed-64 default, `repeat-v1`, model retries `2`, and validator strictness are
unchanged. There is no adaptive fallback or title/cue/text-specific production
logic; publication and Jellyfin behavior are unchanged.

Direct CT108 verification reported PASS / `RC=0` for `py_compile`,
`teddy_discovery_stateful_live_runner_retry_smoke.py`,
`teddy_discovery_stateful_live_runner_timeout_smoke.py`,
`teddy_discovery_stage12_batch_smoke.py`, and `git diff --check`.
No live production retry has been performed after this fix.
