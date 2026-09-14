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
- controller smoke 41/41 PASS
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
| DROP-141 | 173 | 3 / 3 | 929.3987664356828 | 0 | 0 | 0 | PASS / PASS | PASS |

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

## Next Step

Stage12 scope is frozen and CP6 final closure is **PASS**. The final durable
state across 173 titles is:
`PUBLISHED=11`, `FAILED_RETRYABLE=3`, `PENDING=158`, `RUNNING=0`, and
`UNRESOLVED=1` (`FAILED_TERMINAL=0`, `GENERATED=0`,
`SKIPPED_EXISTING_KO=0`). The three retryable failures remain preserved and
are not retried in this closure.

The next candidate checkpoint is preparation for an isolated 128-cue
benchmark, not a full rollout and not a production change.  Do not implement
or execute it in this closure.  When separately authorized, the order is:

1. prepare a benchmark-only 128-cue policy/harness;
2. preserve production `STATEFUL_PART_BATCH_SIZE=16` unchanged;
3. use the CP7B 64-cue results as the baseline;
4. use the same three titles: AT-099, BLOR-289, and DROP-141;
5. run synthetic validation and dependency preflight before any live attempt;
6. compare the 64-cue and 128-cue results only after a successful isolated run.

Expected 128-cue planned parts are AT-099: `12`, BLOR-289: `7`, and
DROP-141: `2`.  No 128-cue implementation or execution has been performed.

Separately evaluate whether existing holdings can use timestamp-aligned
canonical Japanese SRT plus large-chunk ChatGPT KO conversion, while new
downloads continue through the existing automated pipeline. This is a design
option only; it is not a production fallback decision.

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
- Stage12 ACTIVE / CP7B CLOSED / PASS; 128-cue isolated benchmark is only a
  future candidate before any production change
- 작품별 튜닝으로 되돌아가지 않기
- ADN/JUR/HSODA/DVDMS 특정 production logic 금지
- old canonical KO subtitle overwrite 금지
- no unbounded or blind retries; only the frozen generic bounded retry
- Hermes timeout does not trigger immediate same-part retry; resume uses remote pending recovery
- no broad NAS scan
- no automatic publication
- controller/result가 timing authority를 Hermes에 넘기지 않도록 유지
