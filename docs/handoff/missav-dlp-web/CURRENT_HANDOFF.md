# Teddy Downloader / missav-dlp-web — CURRENT HANDOFF

## 2026-09-29 Stage13-F2H pinned completion runtime — FAIL / review required

The F2G blocker was addressed for the scheduled completion/organizer path. An
immutable release was installed at
`/opt/missav-dlp-web/stage9-runtime/releases/26c8657d4bd5c5b767f2f8eb474a80ff9121a150/`
from exact commit `26c8657d4bd5c5b767f2f8eb474a80ff9121a150`. It contains the
24-module local import closure of the completion runner, including
`teddy_title_exclusion.py`, the completion orchestrator, organizer apply,
operation lock, and DVD-ID parser. Release files are read-only; source SHA-256
was checked against `git show` for each archived file. Core hashes:
title exclusion `a4dd0d847cb05a20146f69f62d08ae29e626e997a49c203c1ad70d688b28e1ab`,
completion orchestrator `41cf203b552b246f8095b8025bf281d8633f9e2d893bf886fe430de7c53b38d0`,
organizer apply `559602f0e36f179df243072c5916ddf1009f1d2517ae83207807ae049cf3b93d`.

`/usr/local/sbin/teddy-completion-stage9-runner` was atomically switched to the
version-pinned release. It checks the release marker, sets
`TEDDY_TITLE_LOCK_DIR=/opt/missav-dlp-web/title-locks`, pins `PYTHONPATH` to
that release, and uses `/usr/bin/python3` (3.13.5) as root:root. The previous
wrapper is preserved at
`/opt/missav-dlp-web/backups/stage13-f2h-20260929-1225-teddy-completion-stage9-runner`;
the old `42339ea7...` runtime remains untouched. Release imports and the
completion orchestrator, organizer apply, runner, and process-flock fixture
smokes passed offline. Source order is per-title lock before the existing
global completion operation lock.

Host runtime ↔ web cross-process checks passed in both directions:
same-title contention returned `BUSY`, the host and container observed the
same lock inode, holder termination released the lock, and a second canonical
DVD-ID remained independently acquirable. The production web remains on the
F2F image, delete gate is false, writer health is `READY`, and Discovery DB
mount is read-only.

Stage12 has no systemd/cron automatic launcher. Its documented manual command
uses the checked-out F2F source and requires
`TEDDY_TITLE_LOCK_DIR=/opt/missav-dlp-web/title-locks`; no Stage12 run occurred.
The separate manual `teddy-discovery-jav-reconcile-apply.service` still points
at the old Stage9 runtime and was not invoked; review its role/lock boundary
before claiming broader Discovery-writer exclusion.

**A timer side effect prevents a clean PASS.** During timer restoration,
`systemctl start teddy-completion-stage9.timer` immediately triggered the
scheduled service due to its overdue `OnUnitInactiveSec`. Its result had
`total=0`, `eligible=0`, `applied=0`, and media reconciliation created 0 jobs;
however, it retried one existing media job, which failed and updated that
media-state row (`attempt_count=17161`). The stored error was not exposed. The
failure point relative to NAS metadata publication and Jellyfin notification
cannot be established from the safe result, so those side effects are
**UNKNOWN**, not asserted zero. Present holdings remained 184, organizer
active jobs 0, Stage12 active rows 0, writer health remained ready, and no
delete/provenance operation occurred. The completion timer is currently
inactive (still enabled) to prevent another retry pending review. The F2H
launcher/runtime was not rolled back; its lock checks passed. Before resuming
the timer, inspect the failed media job and decide how to handle its retry.

## 2026-09-29 Stage13-F2G shared title-lock production deployment — INCOMPLETE

The exact F2F web source `26c8657d4bd5c5b767f2f8eb474a80ff9121a150` is
deployed as image `sha256:bac75af6716cd7a0e33aa671b90f9386926d8dc93f64dba201caa6494283e404`
(`missav-dlp-web:stage13f2g-26c8657`). The previous running image
`sha256:40d68b117add00b0dfa85748780d49c3578e670af42d11aa2ae9dfda805dc787`
was retained locally as `missav-dlp-web:rollback-f2g`. Only
`missav-dlp-web` was recreated. It is running with restart count 0; `/login`
and static Library assets return 200, `/` redirects unauthenticated users,
and unauthenticated Library and delete-prepare API requests return 401.

Production Compose/env now persist the host lock root
`/opt/missav-dlp-web/title-locks` at container path `/run/teddy-title-locks`,
with `TEDDY_TITLE_LOCK_DIR=/run/teddy-title-locks` in the web container.
The host directory is root:root mode 0750; lock files are regular files mode
0600. Host completion/systemd, the documented host Stage12 runner, and the web
container currently execute as UID/GID 0; the web container additionally has
GID 988. The host and container saw the same lock device/inode for the
`ADN-785` connectivity probe. Host-held to container and container-held to
host contention both returned `BUSY`; killing the container-side holder
released the kernel lock; a different canonical DVD-ID remained acquirable
while `ADN-785` was held. These were lock-only probes; empty lock files are
left in place by design.

The web feature gate is explicitly `TEDDY_LIBRARY_DELETE_ENABLED=false`.
The Discovery database remains mounted read-only and the writer socket remains
read-only. Writer health is `READY` on host and container. Exact
`ADN-785` `preflight_holding` returned `READY` using a rollback-only
`BEGIN IMMEDIATE`; `present=1`, holding identity, and the current holding count
were unchanged.

Current read-only snapshot: 184 present JAV holdings, 184 unique DVD-IDs, no
duplicates, and no canonical/parse mismatches. Organizer active jobs: 0;
Stage12 `RUNNING`/`GENERATED`: 0; heartbeat: stale `COMPLETE` with no active
title inference.

**Canary remains blocked.** The active production completion wrapper
`/usr/local/sbin/teddy-completion-stage9-runner` pins
`/opt/missav-dlp-web/stage9-runtime` at commit
`42339ea7fb01f62f798baa04d5e774f644b7f46f`; its completion orchestrator and
organizer apply module differ from the F2F integrated source and do not use
the per-title lock. The reconcile apply launcher also points at that old
runtime. Their configured execution UID is root, but setting the lock env
alone cannot provide exclusion while this old source remains active. No host
runner or writer service was run or restarted for this checkpoint.

Stage12 has no persistent systemd service; its documented manual runner uses
the checked-out F2F-integrated module. Any future invocation must explicitly
set `TEDDY_TITLE_LOCK_DIR=/opt/missav-dlp-web/title-locks` in that command's
environment. Do not treat current idle counts as a substitute for this lock.
The next checkpoint must install/activate an exact, version-pinned F2F
completion/organizer runtime and persistent lock-root configuration, then
repeat cross-runtime exclusion. Until that is done:
`SHARED_PER_TITLE_LOCK=NO` for production participants and
`CANARY_READY=NO`. Delete gate stays false; actual delete, Discovery content
write, provenance write, NAS write, Jellyfin refresh, and subtitle generation
remain 0.

## 2026-09-29 Stage13-F2F shared per-title exclusion — PASS (offline/source)

The F2E remaining `SHARED_PER_TITLE_LOCK_UNAVAILABLE` race boundary is closed
for the current organizer/completion, Stage12 batch, and Library delete paths.
They now share `teddy_title_exclusion.try_acquire_title_lock()` and a
non-blocking `fcntl.flock(LOCK_EX | LOCK_NB)` keyed by canonical DVD-ID.

Execution paths are on CT108 `downloader` (the same host namespace documented
in the Stage12 runtime contract). The canonical deployment binds host
`/opt/missav-dlp-web/title-locks` to the web container at
`/run/teddy-title-locks`; host runners use the host path and the web app uses
the container path, which refer to the same bind-backed directory/inodes.
`TEDDY_TITLE_LOCK_DIR` is required by all callers; missing/unsafe lock roots
fail closed. Lock files contain no payload. Future automatic subtitle runners
MUST acquire this same per-title lock.

Lock order is per-title lock before the existing organizer apply lock or
completion `operation_lock`. Stage12's singleton runner lock remains outside
the per-title scope; it does not participate in the opposing delete/completion
lock order. The Stage12 rollout writer lock is acquired only briefly inside
the per-title lock. No StateStore-writer-to-title-lock path was found.

- Organizer apply holds the title lock from before its existing apply lock
  through publish, holding/job updates, source cleanup, and terminal job state.
- Completion `process_one` takes title lock, then `operation_lock`, and holds
  both through canonical publish, holding/job update, and cleanup.
- Stage12 obtains the title lock before durable RUNNING and holds it through
  controller work, publication, Jellyfin recognition, and terminal rollout
  transition. BUSY returns `HELD_TITLE_BUSY` without changing durable state.
- Delete commit and partial mutation resume acquire the same lock after the
  first activity check and Discovery writer preflight. While held they repeat
  activity and identity/manifest validation, then retain the lock through NAS
  mutation, Discovery/Jellyfin reconciliation, provenance finalization, and
  token finalization. Reconcile-only recovery remains available without the
  lock. Busy returns `delete_target_busy`; unavailable lock infrastructure
  returns `delete_exclusion_unavailable`, both before mutation.
- The F2E durable activity guard remains in place as a state sanity check;
  shared flock supplies cross-process exclusion.

Separate-process flock fixtures prove same-title BUSY, different-title
parallelism, release after normal exit, and kernel lock release after process
termination while the empty lock file remains. Organizer, Stage12, and delete
fixtures verify their lock scope and no-work-on-BUSY behavior. Regression
smokes and the full Docker image build passed.

`SHARED_PER_TITLE_LOCK=AVAILABLE` and `TOCTOU_CLOSED=YES` for these integrated
source paths when the canonical host-backed mount/env is deployed. This is
source/fixture evidence only; production deployment has not occurred. Feature
gate remains false, production deploy/restart = NO, actual delete = 0. Stage13
F2G must deploy the shared lock mount/env and verify runtime wiring before any
canary readiness decision.

## 2026-09-29 Stage13-E2D origin forensic — PASS

The exact production rejection for the authenticated ADN-785 delete DRY-RUN
prepare was confirmed:

- response code: `invalid_request_origin`
- guard subreason: `scheme_mismatch`
- browser Origin: `https://downloader.ssikgun.com`
- Flask request view: scheme `http`, host `downloader.ssikgun.com`
- `X-Forwarded-Proto=https`
- `X-Forwarded-Host`: missing
- `Sec-Fetch-Site=same-origin`

Therefore the failure is specifically reverse-proxy/public-origin scheme
normalization. The public host itself matches; the request reaches Flask as
HTTP while the browser correctly identifies the public origin as HTTPS.

No ProxyFix or other app-wide trusted forwarded-header normalization primitive
currently exists. The upstream proxy/trust-hop topology is not sufficiently
documented to justify blindly trusting arbitrary forwarded headers.

Frozen fix direction:

- keep authentication, JSON/intent, Origin, host, and same-site checks;
- do not weaken or remove Origin validation;
- do not trust arbitrary `X-Forwarded-*` headers;
- add a centrally configured trusted public origin (for example
  `TEDDY_PUBLIC_ORIGIN`) and an app-wide helper that parses/canonicalizes that
  configured origin;
- compare browser Origin against that configured trusted public origin and keep
  request-host validation consistent with the configured public host;
- do not hard-code `downloader.ssikgun.com` inside production logic;
- fail closed if the configured public origin is absent or invalid for this
  destructive-intent path.

Safety state remains:

- token issued: NO
- validate reached: NO
- delete/commit endpoint: absent
- NAS/DB/Jellyfin write/delete: 0

Next checkpoint is implementation + fixture validation of the configured
public-origin helper. Production deployment remains a separate checkpoint.


## 2026-09-29 Stage13-E2C manual reproduction — invalid_request_origin confirmed

Teddy manually retried the authenticated production DRY-RUN prepare for
`ADN-785` after the diagnostics-only deployment.

Observed UI-safe error code:

`invalid_request_origin`

This confirms the request passes authentication and the JSON/intent boundary,
then fails inside the origin/same-site portion of the delete-intent guard.

The exact origin subreason is still pending app-log inspection. It must be read
from the bounded diagnostics added in Stage13-E2C and classified as one of the
known safe branches such as `origin_missing`, `scheme_mismatch`,
`host_mismatch`, or `cross_site`.

Safety state remains unchanged:

- token issued: NO
- validate reached: NO
- delete/commit endpoint: absent
- NAS/DB/Jellyfin write/delete: 0

Do not change or relax the guard until the exact logged subreason and sanitized
request/origin/forwarded-header relation are confirmed.


## 2026-09-29 FNS-247 external subtitle parser/alignment replay — PARTIAL

Generic source changes completed in Stage11 subtitle parsing and alignment:

- SRT parsing may drop at most one structurally valid zero-duration cue per
  document. Cue index/text are validated, the original payload hash and byte
  size remain bound to the parsed document, and all other timestamp/content
  validation remains strict. Dropped source indexes are exposed as immutable
  `SubtitleDocument.dropped_cue_indexes` metadata.
- Alignment comparison text replaces only CR/LF with spaces in its derived
  value. Stored cue text and timing remain unchanged; other control characters
  still fail validation.
- No title-specific parser, cue, acceptance, or production path was added.

Offline checks:

- `teddy_discovery_subtitle_text_smoke.py`: PASS, including one-drop admission
  and rejection when more than one zero-duration cue is present.
- `teddy_discovery_alignment_smoke.py`: PASS, including multiline cue text
  preservation, CR/LF comparison normalization, and rejection of tab controls.
- `teddy_discovery_alignment_acceptance_smoke.py`: PASS; frozen acceptance
  gates are unchanged.
- `teddy_discovery_stage11_live_adapters_smoke.py`: not run to completion;
  this environment lacks the `numpy` dependency (`ModuleNotFoundError`).

Exact supplied-input read-only replay:

- JA source: `/var/tmp/FNS-247.user-external-ja.srt`, SHA-256
  `8e645dd1e55304075b03562ae38837012d401a6cb00cb96fc8d54d9df2508598`.
- Baseline ASR was read from the existing stage12 artifact and reconstructed
  in memory; no NAS, Jellyfin, rollout DB, or current KO file was written.
- Parser admitted 313 cues and recorded one dropped cue, original SRT index
  153. All 313 cues reached lexical candidate generation (233 candidates at
  the unchanged 0.80 score floor).
- Alignment did not produce an affine result: strict monotonic selection
  raised `AlignmentAmbiguityError` for equal-strength chains. The same guard
  also fired when candidate score floors were raised to 0.90, 0.95, and 1.00.
  No selector or acceptance threshold was bypassed or weakened.
- Acceptance verdict: **UNRESOLVED / no ACCEPT_HYBRID or REJECT_EXTERNAL
  decision emitted**. Anchor/inlier counts and ratio are not available because
  affine alignment was not inferred. A future checkpoint may address generic
  repeated-text anchor ambiguity; until then, the production external-JA path
  remains fail-closed for this replay.

Source changes and this handoff are committed as `54010d7` and pushed to
`origin/teddy-subtitle-stage11`.

## 2026-09-29 Stage13-E2B prepare-guard forensic — INCOMPLETE

Production manual delete-prepare attempts for `ADN-785` returned HTTP 403
three times. Authentication had already succeeded; therefore the request was
rejected inside the Library delete-intent guard before manifest inspection or
token issuance.

Confirmed safety state:

- prepare HTTP status: 403
- exact branch between `invalid_request_boundary` and
  `invalid_request_origin`: not yet observable from current logs/UI
- token issued: NO
- validate reached: NO
- NAS/DB/Jellyfin write/delete: 0
- production restart/source change during forensic: 0

Current access logs do not record response JSON or the sanitized request/proxy
metadata needed to distinguish the two guard branches. The UI currently turns
all non-success prepare responses into the same generic message.

Next checkpoint is a diagnostics-only hotfix:
1. keep all existing delete-intent checks unchanged;
2. add bounded structured logging for the rejected guard branch and sanitized
   origin/host/forwarded-header metadata;
3. allow the UI to display only an allowlisted safe error code for
   delete-prepare/validate failures;
4. redeploy only the web app and reproduce once.

Do not weaken Origin checking, trust arbitrary forwarded headers, or enable any
delete/commit endpoint.


## 2026-09-28 Stage13-E2 manual prepare attempt — FAIL / forensic required

Teddy manually opened the production File Management delete DRY-RUN for
`ADN-785` from an authenticated browser session. The dialog opened, but the
prepare request did not return a usable PREPARED payload and the UI showed:

`삭제 준비 정보를 확인하지 못했습니다.`

Important safety facts:

- No validate request was reached.
- No delete/commit endpoint exists.
- No NAS/DB/Jellyfin write was performed by this manual attempt.
- The previously bounded internal manifest for ADN-785 was readable, so the
  failure must be narrowed at the production HTTP prepare boundary before any
  source change.

Potential but **unconfirmed** suspect: the prepare guard compares browser
`Origin` against Flask `request.host_url`. Behind the production reverse
proxy, scheme/host normalization may differ (for example external HTTPS versus
internal HTTP) even for a legitimate same-origin browser request. Do not change
this guard until the actual response status/error code and proxy header view are
captured.

Next checkpoint is read-only forensic of the exact production prepare request:
HTTP status, safe JSON error code, relevant app/access log evidence, and
sanitized request/proxy origin-host metadata. Actual deletion remains disabled.


## 2026-09-28 Stage13-E2A current-holdings delta forensic — PASS

The previous Stage13-A/C value of 177 present JAV holdings was a point-in-time
snapshot, not a permanent production invariant.

Current read-only Discovery state:

- present JAV holdings: **184**
- unique DVD-ID: **184**
- MATCHED: **184**
- duplicate DVD-ID: **0**
- canonical/parse mismatch: **0**

Seven holdings have `first_seen_at` after the prior 177 snapshot boundary and
all seven are classified as `NEW_CANONICAL_HOLDING_CONFIRMED`:

- EROFV-313
- SVVRT-086
- NTR-102
- DAL-012
- FTHT-361
- FTHTD-219
- FTHTD-228

Each has `discovered_by=completion-stage9` and one matching COMPLETED organizer
job for the same canonical destination. This confirms the current 184 count is
explained by verified new canonical holdings since the prior snapshot. The
organizer timestamps are completion evidence, not exact filesystem placement
instants.

Historical removal reconstruction remains unavailable because the current
schema does not preserve a complete holding-transition history. Do not infer
that no historical removal ever occurred.

Current Stage12 relationship:

- Stage12 rollout rows remain **173**.
- Current holdings without a Stage12 rollout row: **11**
  (`DAL-012`, `EBWH-296`, `EROFV-313`, `FTHT-361`, `FTHTD-219`,
  `FTHTD-228`, `MIAD-866`, `MIRD-258`, `NTR-102`, `SKMJ-774`,
  `SVVRT-086`).

Frozen Stage13 contract:

- File Management `total_titles` is derived from the **current** read-only
  `storage_root='jav' AND present=1` holdings snapshot at request time.
- Never use 177 (or any other historical count) as a production hard gate.
- Stage12 terminal state remains an optional LEFT JOIN.
- Current holdings without Stage12 rollout rows are valid File Management items.
- Stage13-E2 prepare/validate canaries must compare against the current snapshot
  captured immediately before the canary.

The remaining E2 blocker is only the authenticated same-origin
prepare/validate/replay canary. Actual delete remains disabled.


## 2026-09-28 Post-Stage13 subtitle automation — progress visibility requirement

When the post-Stage13 automatic subtitle workflow for newly completed downloads
is implemented, File Management > `자막 처리 현황` must become the operational
progress view for that automation.

Required visible progress semantics:

- Always show the currently processing DVD-ID when a subtitle job is active.
- Show the current pipeline stage with a short human-readable Korean label
  (for example inventory check, ASR, evidence preparation, Hermes semantic
  translation/review, publication, Jellyfin verification).
- When Hermes is processing split semantic parts, show exact progress as
  `Part n/N`, using the existing controller/runtime progress source rather
  than guessing from elapsed time.
- Preserve the current status summary counts and heartbeat/last-activity
  information, but distinguish active-job progress from aggregate library
  holdings counts.
- Idle state must clearly say there is no current title.
- Retry/failure/unresolved states must remain title-local and expose a concise
  machine-derived reason without subtitle body/raw response/session identity.
- The UI should update from the durable job/controller state so browser reloads
  do not lose the current progress view.
- This requirement belongs to the post-Stage13 new-download subtitle automation
  work; do not expand Stage13 permanent-delete scope to implement it now.


## 2026-09-28 Stage13-C visual acceptance — CLOSED / PASS

Manual authenticated browser verification by Teddy confirmed the final Stage13-C
File Management UI in dark mode.

Accepted visual state:

- Sidebar exposes a single `파일 관리` destination for durable JAV holdings.
- File Management contains `보유 라이브러리` and `자막 처리 현황` subtabs.
- Subtitle processing status is no longer shown in Settings.
- The subtitle status panel, metric cards, badge, labels, and footer now honor
  the application dark theme and remain readable.
- The visible production status panel showed idle state, current title none,
  `PUBLISHED=163`, `PENDING=0`, `FAILED_RETRYABLE=0`,
  `FAILED_TERMINAL=0`, and `UNRESOLVED=10`; its heartbeat was shown as
  stale/old, matching the read-only status source rather than being hidden.
- The manual screenshot showed no catastrophic horizontal overflow or theme
  breakage in the accepted desktop view.

Stage13-C is therefore **CLOSED / PASS**.

The current production web candidate is the Stage13-C6 image built from source
HEAD `b63bd132bc75753b8b1127cb792e42c4b33e8324`
(image prefix previously recorded as `sha256:7f427ebf...`). No rollback is
required.

Next Stage13 work must continue from the frozen permanent-delete plan. Do not
reopen Stage13-C unless a concrete regression is found.


## 2026-09-28 Stage13-C4 manual visual finding — dark-theme defect

Manual authenticated visual inspection confirmed the Stage13-C3/C4 navigation
refactor is present in production, but **Stage13-C remains open** because the
`자막 처리 현황` panel does not honor the application's dark theme.

Observed defect:

- The surrounding File Management page is correctly dark.
- `templates/teddy-subtitle-status.css` still hard-codes light panel,
  metric-card, border, and text colors.
- Unlike the Stage13 Library CSS, it has no
  `html[data-theme="dark"]` overrides.
- The result is a large light status card inside an otherwise dark page.

Required next fix is UI-only:

- add scoped dark-theme overrides for the subtitle-status panel, metric cards,
  text, border, and status badges while preserving meaning-first labels;
- keep light theme unchanged;
- do not change subtitle status API/polling/state semantics;
- validate both light and dark rendering and narrow layout;
- redeploy only the web app and keep DB/NAS/Jellyfin writes at zero.

The production Stage13-C4 candidate remains running until this visual defect is
fixed and manually accepted.


## 2026-09-28 Stage13-C UI information-architecture correction

User clarified the original Files page is **not** the durable JAV library. It
shows downloader-side files only while they remain in the downloader storage;
after the organizer moves a completed title into the canonical JAV library,
that title disappears from the old Files page. This disappearance is the
reason Stage13 exists.

Freeze the UI semantics accordingly:

- The new Stage13 current-holdings Library view is the durable **File
  Management** destination and should become the single sidebar
  `파일 관리` entry.
- Do not keep a second sidebar entry that competes with it as
  `영상 라이브러리`.
- The legacy Files view is transient/downloader-side state, not the permanent
  library. Preserve its functionality, but relocate/rename it under the
  Download area as a secondary view such as `다운로드 파일` / `정리 전 파일`;
  it must not be presented as the primary File Management destination.
- Move the existing `자막 처리 현황` panel out of Settings into the durable
  File Management area. It is operational/library status, not a preference.
- File Management should therefore center on:
  1. current JAV holdings/library (default),
  2. subtitle processing status/monitoring.
- Settings should retain actual configuration/system controls only.
- Existing transient Files playback behavior must remain available after the
  navigation move; no functionality should be silently removed.
- Permanent-delete work later in Stage13 belongs to the durable JAV File
  Management view, never the transient downloader Files view.

This is a Stage13-C information-architecture correction before formal C
closure; production candidate remains deployed pending this UI refinement and
manual visual acceptance.


## 2026-09-28 Stage13-A forensic / contract freeze — PASS

Stage13-A read-only forensic is complete. No source, DB, NAS, Jellyfin, Hermes,
or VM122 production write occurred during the forensic.

### Repository identity

- Branch: `teddy-subtitle-stage11`
- Stage13-A final local HEAD after handoff-only fast-forward:
  `9d6b8b8b590122051ca7c763cb9c7d0e88456795`
- Worktree was clean.
- The prior apparent remote mismatch was caused by a stale
  `origin/teddy-subtitle-stage11` tracking ref; the branch is not present in the
  configured `remote.origin.fetch` refspec. Exact `ls-remote` confirmed the
  server branch at the expected handoff-only commit.

### Stage13-B frozen read-model contract

- File Manager source set is current Discovery holdings, not Stage12 rollout.
- Current present JAV holdings: **177**.
- Stage12 rollout rows: **173**.
- File Manager joins current holdings with Stage12 terminal state using an
  optional/LEFT JOIN boundary. A holding without a Stage12 row must still be
  visible and manageable.
- The four present holdings without a Stage12 rollout row are:
  `EBWH-296`, `MIAD-866`, `MIRD-258`, and `SKMJ-774`. All currently record
  `discovered_by=completion-stage9`. Do not claim they were downloaded after
  Stage12 closure without separate evidence.

### NAS addition-date contract

Read-only bounded sampling used canonical DB paths only. Six sampled titles
(two each from `library-inventory`, `organizer-apply`, and
`completion-stage9`) were checked through the dedicated NAS SSH boundary.
The NAS filesystem was Btrfs. Filesystem birth/creation time was unavailable
for both title directories and media files; directory ctime was not reliable
as final-placement time, and media mtime is not accepted by itself as download
or placement time.

Every one of the 177 current holdings has a matching COMPLETED organizer job
for its exact canonical destination. For 176 titles, publisher job creation
and completion fall on the same KST calendar date, which bounds final placement
to that date and is sufficient for the Stage13 UI date display. One title
crosses a KST date boundary, so its historical `nas_added_at` remains null and
its UI must show `추가 날짜 확인 불가`. Do not invent an approximate date.

For future newly completed titles, record the successful final JAV publication
instant as durable `nas_added_at` provenance so this ambiguity does not recur.

### NAS / mount boundary

In the current CT108 shell namespace, `/mnt/nas-jav` and
`/mnt/nas-downloads` are ordinary paths on the local ext4 root filesystem,
not the JAV NAS mount; `/final` is absent. Therefore:

- `JAV_LOCAL_MOUNT=NOT_PRESENT_IN_CURRENT_NAMESPACE`
- Stage13 metadata/size reads use exact bounded NAS SSH operations.
- Browser playback uses validated canonical title identity through a minimal
  adapter over the existing player/stream behavior.
- Future permanent delete uses a dedicated NAS SSH mutator.
- Do not make the CT108 JAV mount writable or depend on a local RW JAV mount.

### Next checkpoint

Proceed to **Stage13-B — read-only backend / read model**. Implement list/detail,
server-side search, filters, sorting, bounded per-title/library size accounting,
KO / UNRESOLVED / Jellyfin state, NAS addition-date display contract, and the
minimal browser-playback adapter. Do not implement permanent delete yet.


## 2026-09-28 Post-Stage13 next priority — automatic subtitles for newly completed downloads

This requirement is intentionally **outside Stage13** so the Stage13 NAS Library
File Manager can be completed without changing the subtitle production
pipeline.

After Stage13 is CLOSED / PASS, the next priority is to automate subtitle
follow-up for **newly downloaded/completed titles**. Stage12 closed the bounded
rollout for the already-held library; it must not be treated as an ongoing
whole-library job.

Required future behavior:

- Trigger only after a newly downloaded title has completed the existing
  canonical completion/organizer flow and the final JAV holding is durable.
- Read the existing canonical subtitle inventory first. If a valid canonical
  Korean sidecar already exists, finish as a no-op/skip and never overwrite it.
- If Korean subtitles are absent, enqueue exactly that title into a durable,
  resumable, idempotent subtitle job that reuses the proven Stage11 generation
  pipeline and Stage12 publication/Jellyfin-recognition safety contracts.
- Subtitle failure must remain isolated from the completed media: it must not
  undo the download, organizer result, holding, metadata, or Jellyfin media
  item.
- Preserve the existing generic evidence-based rules: no title/cue-specific
  production hardcoding, no broad NAS scan, no direct Jellyfin DB write, and
  no unsafe overwrite of existing KO subtitles.
- Avoid duplicate subtitle work when the same completion event is observed
  more than once; the job identity should be tied to the canonical DVD-ID and
  source/media fingerprint.
- The future automation should be event/queue based around the existing
  completion boundary rather than periodically rerunning the closed Stage12
  173-title rollout.

This is the first post-Stage13 implementation priority. Its exact stage name,
queue schema, trigger point, and rollout contract should be frozen only after a
read-only forensic of the current Stage9 completion hook and the reusable
Stage11/Stage12 single-title boundaries.


## 2026-09-28 Stage12 final closure after bounded staging cleanup

### CURRENT STATUS — Stage12 CLOSED / PASS

This top section is the canonical current status. Older handoff sections below
are retained as historical records and do not override this closure result.

- Audited production source HEAD: `9a06e17d2c954d02979660e740a65e4ecb4b835c`
- Final rollout: 173 titles, `PUBLISHED=163`, `UNRESOLVED=10`,
  `FAILED_RETRYABLE=0`, `RUNNING=0`, `PENDING=0`, `GENERATED=0`.
- All 163 published artifact/report bundles passed the existing mechanical,
  hash, and publication-provenance validators. All 163 NAS sidecars matched
  their recorded artifact hashes. Jellyfin GET-only external subtitle
  recognition passed for all 163; refresh and write count was zero.

The bounded manifest mapped every staging entry to a terminal rollout title.
The local Stage12 temporary staging root had 266 directories, 1,652 files, and
126,891,026 bytes before cleanup; it has zero entries, files, and bytes now.
The remote Stage12 bulk runtime root had 266 directories, 1,388 files, and
114,892,516 bytes, including 988 semantic pending response files; it now has
zero directories, files, and pending responses. Both configured roots remain
in place. Local canonical artifact/report inodes did not overlap staging,
remote staging contained no canonical artifact hashes, and rollout event
provenance did not reference staging paths. Cleanup was limited to the
manifested direct children of those two roots.

The 10 unresolved titles and DB reasons are:

- `STAGE12_UNSAFE_AUDIO_TIMELINE` (8): HMN-899 (sequence 7), NIMA-059,
  PRED-889, SGKI-075, SGKI-106, SNOS-334, SVFLA-014, and SW-216 (sequence 5
  for the latter seven).
- `STAGE12_BASELINE_ASR_NO_SPEECH` (1): NHDTC-250 (sequence 9).
- `SUBTITLE_INVENTORY_INVALID` (1): JUR-750 (sequence 1; final transition
  reason `INITIALIZE_FROM_INVENTORY`).

The final runtime audit found no active title, Stage11/Stage12 runner or
controller, locked runner lock, unfinished heartbeat, active remote task,
ASR production temp entry, or large `/tmp` media file. The persistent Hermes
dashboard/gateway processes had no active Stage12 invocation and no working
directory or open file under the remote staging root. Fixture-based Stage11
controller, live runner, semantic retry-feedback, stream redaction, safe
artifact inspector, ASR temp policy, Stage12 batch/retry/bulk/rollout and
reconciliation smokes passed. Compile and `git diff --check` passed.

Safety and privacy decisions remain frozen: deterministic unsafe source audio
timelines and baseline no-speech outcomes are terminal `UNRESOLVED`; no numeric
confidence-only production gate, non-VAD fallback, threshold relaxation,
timeline repair, or title-specific exception was added. Semantic retry
feedback uses only safe validator metadata; Hermes raw output remains
suppressed; artifact inspection is whitelist-only; new durable reports use
session identity fingerprints without raw values.

Historical privacy limitation: 162 legacy published reports still contain
raw session identity fields (486 fields total). The one report using the new
schema contains three SHA-256 identity fingerprints and no raw session field.
The legacy reports were not modified in place during closure.

Stage12 is **CLOSED / PASS**. Stage13 is **NOT STARTED**.

## 2026-09-28 Stage12 rollout-summary wrapper correction

The HMN-896 result-collection wrapper that exited nonzero was an inline
post-run Python snippet, not a tracked repository utility. It imported
`Stage12RolloutStateStore` and `rollout_counts` from
`teddy_discovery_stage12_rollout`; `rollout_counts` is defined in
`teddy_discovery_stage12_bulk_runner`, while the rollout store's existing
public read-only summary API is `Stage12RolloutStateStore.status_counts()`.
The summary path now uses only the canonical rollout module:
`from teddy_discovery_stage12_rollout import Stage12RolloutStateStore`, then
`store.status_counts()`. It does not import the bulk runner or call its
production entry point. Repository search found no duplicate bad import in
other wrappers or utilities. A temporary read-only fixture verified exit 0
and `PUBLISHED=163`, `FAILED_RETRYABLE=0`, `RUNNING=0`, `UNRESOLVED=10`;
Stage12 batch, retry, bulk-runner, rollout smokes, compile, and diff checks
passed. No production state or runner semantics changed.

## 2026-09-28 HMN-896 final explicit retry canary

At expected HEAD `41517e57bc59d3f536644e91ad49c28fb27d26f8`, the read-only
preflight passed: HMN-896 was `FAILED_RETRYABLE` sequence 3 with reason
`STAGE12_SEMANTIC_OUTPUT_VALIDATION_RETRY_EXHAUSTED`, no active rollout
title, production interpreter/dependencies passed, and the source size/mtime
matched Discovery, rollout, baseline ASR, and targeted-evidence fingerprints.
The safe artifact inspector reported 596 baseline segments, 559 semantic
cues, five targeted windows/results, and five `PRESENT_UNRESOLVED` bindings.
The targeted artifact's baseline hash and source fingerprint matched.

The one authorized retry completed as `PUBLISHED` sequence 6 with reason
`STAGE12_PUBLICATION_AND_JELLYFIN_VERIFIED`. Part 5 attempt 1 failed
`CUE_COUNT_MISMATCH` (`expected=64`, `actual=63`), response 7,169 bytes,
SHA-256 `8ba32b248698b661e8dbe013d71bbd1a896c49250bd4a774b865b3ca92220b20`.
Its reconstructed prompt SHA-256 was
`45747d407699b7eaff495b12b4c8179620c6a54c638e2a447b852c6beae4ea28`.
Attempt 2 included machine-generated validation feedback and passed. Its
reconstructed prompt SHA-256 was
`285b2c2d8dd903dfb7f8cfc04237fa79ad5d5a7e9042efd4aeb6443b69a166e8`.
The accepted response bytes were preserved as the canonical part artifact
(5,434 bytes; SHA-256
`f89870a2b0f1adea3f95383995f2d314c80ebb09600ff4b15e865af5ff39417a`). The
part promotion hard-links the validated pending bytes without rewriting them.
No subtitle or transcript content was copied here.

All six Hermes invocations reported raw output suppression. The canary wrapper
captured child stdout/stderr and emitted only allowlisted numeric/enum/hash
diagnostics; no subtitle body, session identifier, staging path, or raw JSON
was forwarded. The new controller report safe summary found zero raw session
identity fields and three SHA-256 fingerprints. Its hash matched rollout
provenance; the CLEAN artifact hash also matched. The final state counts were
`PUBLISHED=163`, `FAILED_RETRYABLE=0`, `RUNNING=0`, `UNRESOLVED=10`, with zero
active titles and zero non-HMN rollout events after the retry began.

The exact local and remote task staging directories were removed after report
and artifact verification; no target staging input remained. `/tmp` and
`/var/tmp` had zero files over 50 MiB, and the Stage12 heartbeat showed
`COMPLETE` with no active DVD. No other title changed.

The outer result-collection wrapper itself exited nonzero after the production
runner had returned exit code 0 because its post-run code imported
`rollout_counts` from the wrong module. Final state, report/artifact hashes,
other-title event count, and cleanup were then verified with separate
read-only checks. No recovery or additional retry was performed.

## 2026-09-28 Safe subtitle-artifact preflight inspection

The HMN-896 read-only forensic command used recursive `rg` with a title
identifier against the artifact directory. The minified targeted-evidence JSON
contained that identifier, so ripgrep emitted its complete matching line,
including subtitle-bearing fields. This was the direct leak source; the
execution wrapper did not redact or truncate matching file lines. `cat`,
`jq` body projections, or Python printing parsed objects have the same unsafe
property if used on subtitle-bearing artifacts. The body was not copied into
this handoff and is not repeated here.

Added `teddy_discovery_safe_artifact_inspector.py`, a read-only JSON inspector
for ASR, targeted evidence, semantic input/output, review, and controller
report artifacts. It parses internally and emits only artifact kind, exists,
byte size, SHA-256, integer schema version, validated public DVD-ID, source
fingerprint match state, cue/segment/source/window/result counts, allowlisted
targeted status counts, part/count metadata, allowlisted route, and raw-session
field/fingerprint counts. It never emits the supplied path, JSON fragments,
free-form strings, or exception text. Malformed JSON reports only
`INVALID_JSON` with safe size/hash metadata. The helper is available for
future Stage11/Stage12 read-only artifact preflight; production validators and
runners were not changed.

Offline smoke passed: sentinel subtitle/session fields and a sentinel session
path were absent from stdout/stderr for targeted evidence, ASR, semantic
input/output, review, and controller-report fixtures; targeted counts, source
fingerprint match, size/hash were exact; malformed input emitted only a safe
error code. Existing ASR/targeted artifact, semantic translator/review,
Stage11 controller, and Stage12 batch/retry/bulk/rollout smokes passed, as did
compile and `git diff --check`. No HMN-896 retry, rollout write, Hermes call,
publication, or Jellyfin write occurred.

## 2026-09-28 Stage11 durable-report session identity privacy fix

Read-only forensic at expected HEAD `d6366666b9b26824602b7e122fb61a11b7d7f7eb`
found raw session identifiers in three nested identity fields in all 133
local durable Stage11 controller reports inspected. Stage11 uses the
translation identity only when validating existing semantic staging; review
identity values are validated for shape. Stage12, publication, Jellyfin,
reconciliation, and rollout provenance use report/artifact paths and hashes,
not these nested identifiers. Raw identifiers remain necessary in memory for
exact semantic part identity validation and review binding; accepted semantic
staging remains separate from the durable controller report.

New controller reports serialize SHA-256 fingerprints for translation,
source-translation, and review-execution session identities, never the raw
identifiers. Existing reports with legacy raw fields remain readable. When
validating a new fingerprint-only report against semantic staging, the
controller finds the unique staging directory whose basename fingerprint
matches, then performs the existing exact raw identity checks in memory.
Validator, prompt, retry, and publication behavior are unchanged. The Stage12
fixture using the legacy report schema remains compatible.

FNS-235's already-published local controller report was left unchanged. Its
report SHA-256 is bound by its rollout row and artifact preflight, and safely
rewriting it would require changing rollout provenance; this task prohibited
rollout DB writes. The report is local to the Stage12 artifact tree, not
copied to the NAS published subtitle directory. The report hash and published
subtitle artifact hash remain distinct. Other scanned local controller
reports have the same legacy schema; no migration was attempted.

Verification passed: controller smoke (51 checks, including fingerprint-only
serialization and completion replay), stateful parts (65 checks), live-runner
and retry/stream smokes, Stage12 batch/retry/bulk/rollout smokes, compile, and
`git diff --check`. No production semantic invocation, rollout mutation,
publication, or Jellyfin write occurred.

Privacy handling note: during the initial forensic work, one tool output
accidentally exposed the FNS session identifier inside a staging path. The
value is intentionally not reproduced here or in source, logs, or commit
metadata. The execution-stream exposure has been acknowledged to the user;
subsequent inspection avoided value-bearing output. This incident does not
change the existing FNS report or rollout provenance.

## 2026-09-27 Stage11 Hermes raw-output stream containment

Forensic at HEAD `80da72bc02a8218d237760dd8d04dbadf13f7a55` found that the
semantic runner already invoked Hermes with `-Q --quiet`, but the GDTM-091
canary still displayed the CLI's raw `review diff`. The installed `hermes chat
--help` describes quiet mode as suppressing banners, spinners, and tool
previews; it exposes no separate raw-diff/output suppression option. Quiet
mode therefore did not protect this path.

The remote Hermes command had no PTY and no stdout/stderr redirection. The
local runner used `subprocess.Popen(..., stdout=PIPE, stderr=PIPE)` and a
selector, then forwarded each received byte chunk unchanged to the matching
parent stdout/stderr stream. The execution interface merged those parent
streams, so the retained evidence cannot establish whether GDTM's raw diff
came from stdout, stderr, or both. No tee or line filter was involved. The
semantic response traveled separately: Hermes wrote the remote pending JSON,
and `_read_remote_regular_file` captured its bytes for validation. Thus CLI
display output was unnecessary for semantic processing.

The GDTM execution stream did expose response text. The runner itself did not
write a raw stdout/stderr log file; the runtime tree had only the heartbeat
and a 70-byte last-run summary log. The accepted semantic response remains
present as a Stage12 staging artifact (part 12: 6,430 bytes); this is the raw
response artifact, distinct from an execution log. No subtitle body was read
back or copied into this handoff. Filesystem inspection cannot establish the
retention policy of the external execution-stream service.

The live runner now captures both CLI streams only in bounded memory, hashes
them, and never forwards their bytes to stdout, stderr, runner logs, or
heartbeat. It emits only stream byte counts/SHA-256 and exact safe remote
status lines carrying a per-invocation random nonce. Nonzero results retain
SSH/model exit codes plus safe stream digests; arbitrary stderr is never
embedded in an exception. Timeout activity detection still observes captured
bytes and retains the existing inactivity/absolute timeout and remote
cleanup behavior. Other captured SSH errors now use byte counts and hashes
instead of raw stderr. The remote pending JSON read used by the validator is
unchanged.

Offline verification passed: stream fixture (raw sentinels absent from
stdout/stderr/execution log; safe diagnostics, error exit codes and timeout
behavior preserved), stateful parts (65/0), controller (39/0), live runner
(16/0), live runner retry, Stage12 batch/retry/bulk/rollout, Python compile,
and `git diff --check`. No Hermes production invocation, rollout write,
publication, Jellyfin write, prompt/validator change, or retry-count change
was made.

## 2026-09-28 SCOP-830 semantic retry-feedback and stream-redaction canary

At expected HEAD `fa68ec685f9379568d8edb3cc22934632681f1c7`, the explicit
single-title retry preflight passed with a clean worktree, production Python
and audio dependencies, `SCOP-830=FAILED_RETRYABLE` sequence 3, zero active
titles, and matching source identity
`SCOP/SCOP-830/SCOP-830.mp4` (1,714,450,031 bytes; mtime_ns
`1788020170245532124`). The only rollout transitions during this canary were
SCOP-830: `FAILED_RETRYABLE -> RUNNING -> GENERATED -> PUBLISHED`, sequences
3 -> 4 -> 5 -> 6.

Part 3 attempt 1 failed `INVALID_KO / KO_CONTROL_CHARACTER` at cue ordinal 36.
Its semantic query UTF-8 SHA-256 was
`b3434294bc8ae497226806c7a05bd65702f46caf0a1dfb84d84c534e77e5a532`; the raw
response was 7,846 bytes with SHA-256
`15c903a08e07b1bea74e52329dc5649d695832d8903877d2f8df517adab9a2ac`.
Attempt 2 included the machine-generated validation feedback. Its query
UTF-8 SHA-256 was
`369516e74474f8fd13e53ae3887846cd7289b3db8e836baf397dec893af6af96`; the
validated response was 7,850 bytes with SHA-256
`cc7cee36932fc4a3f6373717909ef4eed9e0bb9d7ad82c7fbd6656c3351d26fd`.
Attempt 2 passed. All 13 parts completed; final semantic cue count was 786.
No response or subtitle text was copied into this handoff.

Every Hermes call reported `HERMES_RAW_OUTPUT_SUPPRESSED=YES`; stdout/stderr
were represented only by byte counts and SHA-256 digests, plus allowlisted
model/remote exit status. No raw diff or subtitle body appeared in the runner
output, execution stream, or structured heartbeat. The runner does not persist
its stdout/stderr streams. The runtime last-run summary file was 70 bytes; its
contents were not read, so that file is not independently attested here.
Heartbeat ended `COMPLETE`; no active RUNNING/GENERATED title remained. The
published artifact and report were hash-verified, and Jellyfin external
subtitle recognition was verified. Final counts: `PUBLISHED=161`,
`FAILED_RETRYABLE=2`, `RUNNING=0`, `UNRESOLVED=10`. No other title state
changed.

After verifying all 13 remote pending response hashes against the local
canonical parts, the exact per-session remote and local staging copies were
removed (remote/local cleanup PASS; 16 local files, 382,145 bytes removed).
The published artifact and controller report remain in their durable
artifact directory. No other title's staging or runtime data was touched.

## 2026-09-28 FNS-235 retry-feedback canary — session-id report exposure

At expected HEAD `42165a2100bc640042f87ec55f184cf67bf21a30`, read-only
preflight passed with FNS-235 `FAILED_RETRYABLE` sequence 3, zero active
titles, production Python/dependencies, and matching NAS source identity
`FNS/FNS-235/FNS-235.mp4` (3,914,686,408 bytes; mtime_ns
`1788081907263298717`). The retry completed all 10 semantic parts and
publication/Jellyfin verification. Part 7 attempt 1 failed
`SESSION_ID_MISMATCH` at `part.session_id`, response 4,896 bytes with SHA-256
`b7a68314cf662f409ec0fea236bc44a8298661aa91db83c193d07683079cdc62`.
The part-query UTF-8 SHA-256 values were
`aa4ac93df846e9c230cbfd87fc06fa5717e4fef9844f965dc65274209aababba`
(attempt 1) and
`952d23645c6fb03bc9af77bb1ef6663b7627e41a00be09b0a1d7cd0bb414261c`
(attempt 2, with validator feedback). Attempt 2 passed; its accepted response
was 4,896 bytes with SHA-256
`425b4911932e321783cf3b43e022ea1ce2f0e959571ccbba27acf018cf9a4f39`.

The production runner completed `FAILED_RETRYABLE -> RUNNING -> GENERATED ->
PUBLISHED`, sequences 3 -> 4 -> 5 -> 6, with final reason
`STAGE12_PUBLICATION_AND_JELLYFIN_VERIFIED`. The only rollout events during
the canary belonged to FNS-235. Final counts were `PUBLISHED=162`,
`FAILED_RETRYABLE=1`, `RUNNING=0`, `UNRESOLVED=10`; publication and Jellyfin
external visibility were verified.

All five Hermes invocations reported `HERMES_RAW_OUTPUT_SUPPRESSED=YES`. The
canary wrapper captured child stdout/stderr in memory and emitted only
allowlisted fields; it suppressed the runner's session/progress lines, so no
actual session identifier or subtitle body appeared in the user-visible
stdout/stderr or execution stream. Heartbeat and runtime summary had no
session identifier. However, a safe exact-value presence check found the
actual generated session identifier in two fields of the durable Stage11
controller report: `review_result_identity.source_translation_session_id`
and `translation_result_identity.session_id`. The identifier is deliberately
not recorded here. This violates the canary's session-id privacy requirement
even though stream redaction worked. The report and rollout row were not
rewritten; mutating a published artifact and its rollout provenance was
outside this canary's safe completion path.
No other title was run.

The run-specific local staging directory remains (13 files, 239,697 bytes,
zero pending files); remote staging cleanup was not verified after detecting
the report exposure. The heartbeat reached `COMPLETE`, active rollout titles
are zero, and `/tmp` contains no files over 50 MiB. Do not start another title
until the report's session-id emission/storage contract is addressed.

## 2026-09-27 GDTM-091 semantic retry-feedback production canary

At expected HEAD `512e8de3459d440021302674ba0feefcebef2b4b`, read-only
preflight confirmed a clean worktree, `GDTM-091=FAILED_RETRYABLE` sequence 3
with reason `STAGE12_SEMANTIC_OUTPUT_VALIDATION_RETRY_EXHAUSTED`, no active
rollout title, and production interpreter/dependency PASS. Source identity
matched Discovery, rollout, and current NAS: `GDTM/GDTM-091/GDTM-091.mp4`,
2,841,873,974 bytes, mtime_ns `1788070014563915057`.

Part 12 attempt 1 used a 3,022-byte prompt, SHA-256
`df7752671d224f0683ef6e0c62c7ed40c9546a22d86d3bb41bfd374c9dd45522`. It
failed `INVALID_KO`, subcode `KO_CONTROL_CHARACTER`, cue ordinal 2. The
rejected response was 6,440 bytes, SHA-256
`ebba1d7afef8a05056ee16b61c15f979b1434a8db5d7d7e4af2701188513268c`.
Attempt 2 used a 3,245-byte prompt, SHA-256
`64613974408042798e410cdd1ca257b8186e4ca2f5dca11d30e67963cfa0d0df`. The
Hermes prompt record confirms it included the exact safe feedback suffix for
`INVALID_KO`, `KO_CONTROL_CHARACTER`, part 12, cue ordinal 2. It passed
validation. The accepted response payload was 6,430 bytes, SHA-256
`0973216e6c537cc69d86aad1306c78ae96d30e0e27c5403258a89bb404e40de0`.

**Logging disclosure:** the Hermes CLI emitted a raw review diff for the
attempt-1 response to the live execution stream, including subtitle body.
Stage11's own validation diagnostic line contained only safe metadata, and
the retry feedback and this handoff contain no subtitle body. The CLI diff
was not copied into the report or retained in the handoff. Attempt 2 passed;
the runner continued through the remaining Stage11 parts and publication.

The one-title run finished `PUBLISHED`, sequence 6, reason
`STAGE12_PUBLICATION_AND_JELLYFIN_VERIFIED`. Final counts:
`PUBLISHED=160`, `FAILED_RETRYABLE=3`, `RUNNING=0`, `UNRESOLVED=10`. Stage12
selected and processed only GDTM-091; no other title state changed.

The runner exited with heartbeat `COMPLETE` and no active rollout title. No
runner process remained; `/tmp` had no file larger than 100 MiB and `/var/tmp`
had 37,546,962,944 bytes free. Per-session Stage12 staging remains in the
runtime area as run evidence (19 files); it was not manually deleted.

## 2026-09-27 MAAN-1193 semantic retry-feedback production canary

At expected HEAD `0459f77d551273b5166d0227bd67965261d0efd5`, read-only
preflight confirmed a clean worktree, `MAAN-1193=FAILED_RETRYABLE` sequence 5
with reason `STAGE12_SEMANTIC_OUTPUT_VALIDATION_RETRY_EXHAUSTED`, matching
source identity (`MAAN/MAAN-1193/MAAN-1193.mp4`, 2,431,792,344 bytes,
mtime_ns `1788865578276147930`), no active rollout title, and passing
production interpreter/dependency checks.

The authorized single-title retry used the new feedback contract. For part 9,
attempt 1's unchanged base prompt was 3,020 bytes, SHA-256
`10ce370bead05ea1efaaba30c37bc60e674e96727eaa9d372d5a437cffed969a`. It
failed `INVALID_KO`, subcode `KO_EMPTY_OR_WHITESPACE`, cue ordinal 8. The
rejected response was 4,993 bytes, SHA-256
`fc36ea51c15ac83d97dd328c972ab10c9309e21811136900ae4424fd5c55160c`.

Attempt 2 used a 3,244-byte prompt, SHA-256
`61c106f558eb69ba5e419b8d9cff678729287a02afab67a369f842c21650a4ab`. Its
prompt record confirms that it included `INVALID_KO`,
`KO_EMPTY_OR_WHITESPACE`, and ordinal 8 as machine-generated feedback. It
passed validation. The accepted response payload was 5,207 bytes, SHA-256
`a0b76396ec3ffda18d11c010d8157b022d90fc1bb31711fbd65ee2240188550c`. The
feedback/log diagnostics contained no subtitle text or rejected response
body. All ten parts covering 603 cues validated; the complete result SHA-256
was `6584a9a802d510a9afc486b3dbd815bd4994262e78fedb1617d5c82cc49d97b2`.

Stage12 processed exactly one title. `MAAN-1193` finished `PUBLISHED`,
sequence 8, reason `STAGE12_PUBLICATION_AND_JELLYFIN_VERIFIED`. Final counts:
`PUBLISHED=159`, `FAILED_RETRYABLE=4`, `RUNNING=0`, `UNRESOLVED=10`. No other
title was selected or changed.

The runner exited with heartbeat `COMPLETE` and no active rollout title. No
runner process remained; `/tmp` had no file larger than 100 MiB and `/var/tmp`
had 37,550,080,000 bytes free. The Stage12 per-session staging artifacts
(validated semantic parts/input/result) remain in the runtime staging area as
run evidence; no separate audio temporary workspace remained. No recovery or
additional retry was performed.

## 2026-09-27 MAAN-1193 semantic retry contract forensic and fix

Read-only forensic of the MAAN-1193 sequence-5 canary confirmed that part 9's
two failed requests were separate user-message turns in the existing Hermes
session. The profile's read-only message history records them at
2026-09-27 05:11:23.837871 UTC and 05:12:51.278167 UTC. Both prompt messages
were 3,020 bytes with SHA-256
`10ce370bead05ea1efaaba30c37bc60e674e96727eaa9d372d5a437cffed969a`.
The reconstructed base64 CLI query payload was 4,028 bytes with SHA-256
`6228ace347bd1eb3e5e9a17d7094b2cf42e0e0eb2a1cb48694d898d34eda6de8`.
Both requests referenced the same immutable semantic input, SHA-256
`60968f77cc913b1dc40769e3593192a106036693847ce2b6211e76b9fa03e84c`.
The two prompt records had no validation feedback. The runner removed the
first rejected remote pending response before issuing attempt 2, then reused
the same part query and session. No provider request ID was persisted; the
session's aggregate API-call counter cannot identify these two calls. No
explicit temperature or seed was passed by the runner, and the provider's
effective defaults were not recoverable. There is no evidence of local
pending-response reuse or provider caching; caching cannot be ruled out.

Cause: generic retry-contract bug (A). Before this change a validation retry
made a distinct model request but repeated the same prompt without telling the
model what predicate failed. The prompt requires Korean output for each cue
and validator requires nonempty Korean, but it does not state an empty-output
exception for non-speech cues. No direct prompt/validator contradiction was
found. The rejected part-9 cue had a nonempty 9-character Japanese source;
only structural metadata was inspected. Its rejected Korean output and all
other subtitle text remain excluded from this handoff.

The second attempt now appends a machine-generated feedback block built only
from safe validator enums and numeric/location fields. The first attempt's
query is byte-for-byte unchanged. `INVALID_KO` feedback carries its subcode
and cue ordinal; count mismatch carries expected/actual counts; session
mismatch states the required fixed contract location. The feedback includes
no source or rejected response text. Validators, output acceptance, prompt
semantics on the first attempt, and the one-retry limit are unchanged.

Verification passed: stateful parts (65/0), controller (39/0), live runner
(16/0), live runner retry (PASS), Stage12 batch/retry/bulk/rollout (all PASS),
compile, and `git diff --check`. Retry smoke proves the first query is
unchanged, second query and hash differ, safe failure metadata is included,
sentinel subtitle text is absent, and a valid first response does not retry.
No Hermes production invocation, MAAN-1193 retry, rollout DB write,
publication, or Jellyfin write was performed.

## 2026-09-27 MAAN-1193 semantic diagnostic retry canary

At expected HEAD `82d417a450bf881ec926a73fab907400559c254e`, preflight
confirmed a clean worktree, `MAAN-1193=FAILED_RETRYABLE` at sequence 3 with
reason `STAGE12_SEMANTIC_OUTPUT_VALIDATION_RETRY_EXHAUSTED`, no active
`RUNNING`/`GENERATED` titles, and matching Discovery/NAS source identity:
`MAAN/MAAN-1193/MAAN-1193.mp4`, 2,431,792,344 bytes,
mtime_ns `1788865578276147930`. Production Python, NumPy, and PyAV preflight
passed.

The one authorized explicit retry transitioned MAAN-1193 from
`FAILED_RETRYABLE` sequence 3 to `RUNNING` sequence 4, then back to
`FAILED_RETRYABLE` sequence 5 with reason
`STAGE12_SEMANTIC_OUTPUT_VALIDATION_RETRY_EXHAUSTED`. Part 9 failed
`INVALID_KO` on both attempts. Both responses were 4,993 bytes with identical
SHA-256 `fc36ea51c15ac83d97dd328c972ab10c9309e21811136900ae4424fd5c55160c`,
so both attempts returned the same payload. The exact predicate was
`KO_EMPTY_OR_WHITESPACE`, at 1-based cue ordinal 8. No response or subtitle
text, nor session ID, was retained in this handoff.

Final counts remain `PUBLISHED=158`, `FAILED_RETRYABLE=5`, `RUNNING=0`,
`UNRESOLVED=10`. No other title state changed. No artifact/report was
accepted, and publication/Jellyfin were not reached. The runner completed
with one title processed and no active title left behind. Both rejected
remote pending responses were cleaned by the retry path. The private
`/var/tmp` capture was removed after extracting safe diagnostics; `/tmp` had
no files over 100 MiB, `/var/tmp` had 35 GiB free, and 8.5 GiB RAM was
available. A pre-existing Stage11 staging directory remained with content
timestamps predating the canary; it was left intact. No new artifact/report
directory appeared. No recovery or second retry was performed.

## 2026-09-27 Stage11 semantic validation body-free diagnostics

Added generic safe diagnostics for rejected stateful semantic parts without
changing validator predicates, retry count, prompt, or output acceptance. The
validation exception carries its reason code plus safe optional fields for an
`INVALID_KO` subcode and 1-based cue ordinal, cue-count expected/actual values,
or the fixed `part.session_id` location. The Stage11 live runner records the
part number, retry attempt, response byte length, and SHA-256 alongside the
validation code. It no longer logs the session identifier on this rejection
line. No response body or subtitle fields are logged.

`INVALID_KO` output predicates now have distinct safe subcodes:
`KO_REQUIRED`, `KO_NOT_EXACT_STRING`, `KO_EMPTY_OR_WHITESPACE`,
`KO_TEXT_LIMIT`, `KO_CONTROL_CHARACTER`, and `KO_RUNAWAY_REPETITION`.
Existing source-cue integrity predicates retain `INVALID_KO` and carry separate
source-cue subcodes; an unrecognized legacy path is marked
`INVALID_KO_UNCLASSIFIED`. Ordinals are 1-based within the part.

Offline verification passed: stateful parts smoke (65 PASS / 0 FAIL), live
runner retry smoke (including body-sentinel redaction and payload digest),
stateful controller smoke (39 PASS / 0 FAIL), live runner smoke (16 PASS / 0
FAIL), Stage12 batch, retry, bulk runner, and rollout smokes, Python compile,
and `git diff --check`. No Hermes invocation, production retry, rollout DB
write, publication, or Jellyfin write was performed.

## 2026-09-26 SW-216 explicit retry production canary

Before retry, SW-216 was `FAILED_RETRYABLE`, sequence 3, reason
`STAGE12_TITLE_FAILURE`; counts were `PUBLISHED=158`,
`FAILED_RETRYABLE=6`, `RUNNING=0`, `UNRESOLVED=9`. The canonical replay
recorded the **production fail point** at frame 438 / PTS 457,093: signed
peak drift 66.292 ms exceeded the 64 ms three-decoded-frame bound. Separately,
the full replay EOF diagnostic showed signed drift +63.738 s and corrected
EOF sample mismatch −1. Maximum single-frame correction was 21.313 ms (one
decoded-frame duration); the recorded fail point was cumulative peak drift,
not an EOF failure. The replay procedure recorded matching source
path/size/mtime against rollout identity. Current NAS source matched:
`SW/SW-216/SW-216.mp4`, 4,172,018,393 bytes, mtime_ns
`1788082693280273595`. No duplicate/backward PTS violation was recorded.

At expected production HEAD
`22f5e75d338fa6b80356de23e465037c6fcc721e`, the single explicit retry passed
production interpreter, clean worktree, expected sequence, exact source
identity, and zero-active-title preflights. It transitioned
`FAILED_RETRYABLE -> RUNNING -> UNRESOLVED`, sequence `3 -> 4 -> 5`.
Production reproduced `ASRAudioUnsafeTimelineError: peak net sample-clock
drift exceeds three decoded frames`; Stage12 recorded reason
`STAGE12_UNSAFE_AUDIO_TIMELINE` and outcome `UNSAFE_AUDIO_TIMELINE`. Final
counts are `PUBLISHED=158`, `FAILED_RETRYABLE=5`, `RUNNING=0`,
`UNRESOLVED=10`.

No baseline artifact/report was stored. The typed Stage11 failure stopped
before external subtitle evidence lookup/alignment and publication/Jellyfin.
Only SW-216 was selected; no other title was processed. Temporary ASR
cleanup reported PASS; the production temp root was empty afterward, `/tmp`
had no files over 100 MiB, `/var/tmp` had 35 GiB free, and 8.5 GiB RAM was
available. No recovery or second retry was performed.

## 2026-09-26 SNOS-334 explicit retry production canary

Before retry, SNOS-334 was `FAILED_RETRYABLE`, sequence 3, reason
`STAGE12_TITLE_FAILURE`; counts were `PUBLISHED=158`,
`FAILED_RETRYABLE=7`, `RUNNING=0`, `UNRESOLVED=8`. The canonical full replay
recorded cumulative peak signed drift +12.322 s beyond the existing
three-decoded-frame bound at frame 2,323 / PTS 2,390,035, corrected EOF
sample mismatch 0, and maximum single-frame correction 0.667 ms. The replay
procedure recorded matching source path/size/mtime against rollout identity.
Current NAS source matched that identity: `SNOS/SNOS-334/SNOS-334.mp4`,
4,404,422,746 bytes, mtime_ns `1788083516029248371`. The replay identified
the cumulative peak as the fail point; it recorded no duplicate/backward PTS
or per-frame correction bound violation.

At expected production HEAD
`f476e2a8ca377fbd8507a9d871dd236a77d935c1`, the single explicit retry passed
production interpreter, clean worktree, expected sequence, exact source
identity, and zero-active-title preflights. It transitioned
`FAILED_RETRYABLE -> RUNNING -> UNRESOLVED`, sequence `3 -> 4 -> 5`.
Production reproduced `ASRAudioUnsafeTimelineError: peak net sample-clock
drift exceeds three decoded frames`; Stage12 recorded reason
`STAGE12_UNSAFE_AUDIO_TIMELINE` and outcome `UNSAFE_AUDIO_TIMELINE`. Final
counts are `PUBLISHED=158`, `FAILED_RETRYABLE=6`, `RUNNING=0`,
`UNRESOLVED=9`.

No baseline artifact/report was stored. The typed Stage11 failure stopped
before external subtitle evidence lookup/alignment and publication/Jellyfin.
Only SNOS-334 was selected; no other title was processed. Temporary ASR
cleanup reported PASS; the production temp root was empty afterward, `/tmp`
had no files over 100 MiB, `/var/tmp` had 35 GiB free, and 8.5 GiB RAM was
available. No recovery or second retry was performed.

## 2026-09-26 SGKI-106 explicit retry production canary

Before retry, SGKI-106 was `FAILED_RETRYABLE`, sequence 3, reason
`STAGE12_TITLE_FAILURE`; counts were `PUBLISHED=158`,
`FAILED_RETRYABLE=8`, `RUNNING=0`, `UNRESOLVED=7`. The canonical full replay
recorded cumulative peak signed drift +20.141 s beyond the existing
three-decoded-frame bound at frame 1,294 / PTS 1,341,904, corrected EOF
sample mismatch 0, and maximum single-frame correction 0.667 ms. The replay
procedure recorded matching source path/size/mtime against rollout identity.
Current NAS source matched that identity: `SGKI/SGKI-106/SGKI-106.mp4`,
4,898,003,063 bytes, mtime_ns `1788274311454167056`. The replay identified
the cumulative peak as the fail point; it recorded no duplicate/backward PTS
or per-frame correction bound violation.

At expected production HEAD
`bd52ae98ac4848480e31791316868aad4ad6d635`, the single explicit retry passed
production interpreter, clean worktree, expected sequence, exact source
identity, and zero-active-title preflights. It transitioned
`FAILED_RETRYABLE -> RUNNING -> UNRESOLVED`, sequence `3 -> 4 -> 5`.
Production reproduced `ASRAudioUnsafeTimelineError: peak net sample-clock
drift exceeds three decoded frames`; Stage12 recorded reason
`STAGE12_UNSAFE_AUDIO_TIMELINE` and outcome `UNSAFE_AUDIO_TIMELINE`. Final
counts are `PUBLISHED=158`, `FAILED_RETRYABLE=7`, `RUNNING=0`,
`UNRESOLVED=8`.

No baseline artifact/report was stored. The typed Stage11 failure stopped
before external subtitle evidence lookup/alignment and publication/Jellyfin.
Only SGKI-106 was selected; no other title was processed. Temporary ASR
cleanup reported PASS; the production temp root was empty afterward, `/tmp`
had no files over 100 MiB, `/var/tmp` had 35 GiB free, and 8.5 GiB RAM was
available. No recovery or second retry was performed.

## 2026-09-26 SGKI-075 explicit retry production canary

Before retry, SGKI-075 was `FAILED_RETRYABLE`, sequence 3, reason
`STAGE12_TITLE_FAILURE`; counts were `PUBLISHED=158`,
`FAILED_RETRYABLE=9`, `RUNNING=0`, `UNRESOLVED=6`. The canonical full replay
recorded cumulative peak signed drift +21.554 s beyond the existing
three-decoded-frame bound at frame 1,275 / PTS 1,305,616, corrected EOF
sample mismatch −1, and maximum single-frame correction 0.667 ms. The replay
procedure recorded matching source path/size/mtime against rollout identity.
Current NAS source matched that identity: `SGKI/SGKI-075/SGKI-075.mp4`,
4,714,099,215 bytes, mtime_ns `1788055869233598097`. The replay identified
the cumulative peak as the fail point; it recorded no duplicate/backward PTS
or per-frame correction bound violation.

At expected production HEAD
`d7b850516b869d72e2c33bd6616c068d9c2410ef`, the single explicit retry passed
production interpreter, clean worktree, expected sequence, exact source
identity, and zero-active-title preflights. It transitioned
`FAILED_RETRYABLE -> RUNNING -> UNRESOLVED`, sequence `3 -> 4 -> 5`.
Production reproduced `ASRAudioUnsafeTimelineError: peak net sample-clock
drift exceeds three decoded frames`; Stage12 recorded reason
`STAGE12_UNSAFE_AUDIO_TIMELINE` and outcome `UNSAFE_AUDIO_TIMELINE`. Final
counts are `PUBLISHED=158`, `FAILED_RETRYABLE=8`, `RUNNING=0`,
`UNRESOLVED=7`.

No baseline artifact/report was stored. The typed Stage11 failure stopped
before external subtitle evidence lookup/alignment and publication/Jellyfin.
Only SGKI-075 was selected; no other title was processed. Temporary ASR
cleanup reported PASS; the production temp root was empty afterward, `/tmp`
had no files over 100 MiB, `/var/tmp` had 35 GiB free, and 8.5 GiB RAM was
available. No recovery or second retry was performed.

## 2026-09-26 PRED-889 explicit retry production canary

Before retry, PRED-889 was `FAILED_RETRYABLE`, sequence 3, reason
`STAGE12_TITLE_FAILURE`; counts were `PUBLISHED=158`,
`FAILED_RETRYABLE=10`, `RUNNING=0`, `UNRESOLVED=5`. The canonical replay
recorded cumulative peak signed drift +17.942 s beyond the existing
three-decoded-frame bound at frame 1,780 / PTS 1,847,728, corrected EOF
sample mismatch 0, and maximum single-frame correction 0.667 ms. The replay
procedure recorded matching source path/size/mtime against rollout identity.
Current NAS source matched that identity: `PRED/PRED-889/PRED-889.mp4`,
3,586,684,183 bytes, mtime_ns `1788071473288888127`. The replay identified
the cumulative peak as the fail point; it recorded no duplicate/backward PTS
or per-frame correction bound violation.

At expected production HEAD
`6b4bec621feecbd63a2d1d588908fdfdb3f5556e`, the single explicit retry passed
production interpreter, clean worktree, expected sequence, exact source
identity, and zero-active-title preflights. It transitioned
`FAILED_RETRYABLE -> RUNNING -> UNRESOLVED`, sequence `3 -> 4 -> 5`.
Production reproduced `ASRAudioUnsafeTimelineError: peak net sample-clock
drift exceeds three decoded frames`; Stage12 recorded reason
`STAGE12_UNSAFE_AUDIO_TIMELINE` and outcome `UNSAFE_AUDIO_TIMELINE`. Final
counts are `PUBLISHED=158`, `FAILED_RETRYABLE=9`, `RUNNING=0`,
`UNRESOLVED=6`.

No baseline artifact/report was stored. The typed Stage11 failure stopped
before external subtitle evidence lookup/alignment and publication/Jellyfin.
Only PRED-889 was selected; no other title was processed. Temporary ASR
cleanup reported PASS; the production temp root was empty afterward, `/tmp`
had no files over 100 MiB, `/var/tmp` had 35 GiB free, and 8.5 GiB RAM was
available. No recovery or second retry was performed.

## 2026-09-26 HMN-899 explicit retry production canary

Before retry, HMN-899 was `FAILED_RETRYABLE`, sequence 5, reason
`STAGE12_TITLE_FAILURE`; counts were `PUBLISHED=158`,
`FAILED_RETRYABLE=11`, `RUNNING=0`, `UNRESOLVED=4`. The canonical full replay
recorded the unsafe peak crossing at frame 1,690 / PTS 1,730,560, peak signed
drift +20.218 s, corrected EOF mismatch −1 sample, and maximum single-frame
correction 0.667 ms. The replay procedure recorded matching source
path/size/mtime against rollout identity. Current NAS source matched that
identity: `HMN/HMN-899/HMN-899.mp4`, 3,847,055,679 bytes, mtime_ns
`1788055221873611116`. No duplicate/backward PTS or per-frame correction
bound violation was indicated; the recorded fail point was the cumulative
peak-drift bound.

At expected production HEAD
`99e12455030a8b681efa1c2499d465eace4aedfa`, the single explicit retry passed
production interpreter, clean worktree, expected sequence, source identity,
and zero-active-title preflights. It transitioned
`FAILED_RETRYABLE -> RUNNING -> UNRESOLVED`, sequence `5 -> 6 -> 7`.
Production reproduced `ASRAudioUnsafeTimelineError: peak net sample-clock
drift exceeds three decoded frames`; Stage12 recorded reason
`STAGE12_UNSAFE_AUDIO_TIMELINE` and outcome `UNSAFE_AUDIO_TIMELINE`. Final
counts are `PUBLISHED=158`, `FAILED_RETRYABLE=10`, `RUNNING=0`,
`UNRESOLVED=5`.

No baseline artifact/report was stored. The typed Stage11 failure stopped
before external subtitle evidence lookup/alignment and publication/Jellyfin.
Only HMN-899 was selected; no other title was processed. Temporary ASR
cleanup reported PASS; the production temp root was empty afterward, `/tmp`
had no files over 100 MiB, `/var/tmp` had 35 GiB free, and 8.5 GiB RAM was
available. No recovery or second retry was performed.

## 2026-09-26 NIMA-059 explicit retry production canary

Before retry, NIMA-059 was `FAILED_RETRYABLE`, sequence 3, with reason
`STAGE12_TITLE_FAILURE`; counts were `PUBLISHED=158`,
`FAILED_RETRYABLE=12`, `RUNNING=0`, `UNRESOLVED=3`. The canonical replay
record showed a deterministic peak signed drift beyond the existing
three-decoded-frame bound at frame 192,407 / PTS 197,029,183, corrected EOF
sample mismatch 0, and a maximum single correction of 20.833 µs. Its replay
procedure recorded matching source path/size/mtime against rollout identity.
The current NAS source matched that identity: path
`NIMA/NIMA-059/NIMA-059.mp4`, 3,046,116,440 bytes, mtime_ns
`1788070334697909916`. The recorded original EOF reconciliation failure was
therefore consistent with the replay's earlier unsafe-peak finding; no
duplicate/backward or over-one-frame correction was identified.

At expected production HEAD
`81b2657ea53ab88e7fac631a66271065f16306d3`, the single explicit retry passed
production interpreter, clean worktree, expected sequence, exact source
identity, and zero-active-title preflights. It transitioned
`FAILED_RETRYABLE -> RUNNING -> UNRESOLVED`, sequence `3 -> 4 -> 5`. Production
reproduced `ASRAudioUnsafeTimelineError: peak net sample-clock drift exceeds
three decoded frames`; Stage12 recorded reason
`STAGE12_UNSAFE_AUDIO_TIMELINE` and outcome `UNSAFE_AUDIO_TIMELINE`. Final
counts are `PUBLISHED=158`, `FAILED_RETRYABLE=11`, `RUNNING=0`,
`UNRESOLVED=4`.

No baseline artifact/report was stored. The typed Stage11 failure stopped
before external subtitle evidence lookup/alignment and publication/Jellyfin.
The immutable selection contained only NIMA-059, with no other title
processed. Temporary ASR cleanup reported PASS; the production ASR temp root
was empty afterward, `/tmp` had no files over 100 MiB, `/var/tmp` had 35 GiB
free, and 8.5 GiB RAM was available. No recovery or second retry was
performed.

## 2026-09-26 SVFLA-014 explicit retry production canary

At expected production HEAD
`5bb175dd655f24af9d6695e4e0e1424e60be269d`, the authorized one-title retry
passed production interpreter, exact repository/worktree, rollout sequence,
source fingerprint, and zero-active-title preflights. The source fingerprint
matched at 8,577,682,550 bytes and mtime_ns `1788086386432050851`. The
8,577,682,550-byte source was copied under the disk-backed
`/var/tmp/teddy-stage11-asr-production` root; temp capacity preflight passed.

SVFLA-014 transitioned `FAILED_RETRYABLE -> RUNNING -> UNRESOLVED`, sequence
`3 -> 4 -> 5`. Full-title processing reproduced the unsafe timeline at the
existing three-decoded-frame bound: `ASRAudioUnsafeTimelineError`,
“peak net sample-clock drift exceeds three decoded frames.” Stage12 recorded
reason `STAGE12_UNSAFE_AUDIO_TIMELINE` and outcome
`UNSAFE_AUDIO_TIMELINE`. Final counts are `PUBLISHED=158`,
`FAILED_RETRYABLE=12`, `RUNNING=0`, `UNRESOLVED=3`.

The typed Stage11 failure stopped before baseline artifact persistence,
external subtitle evidence lookup/alignment, and publication/Jellyfin. The
rollout row has null artifact/report paths and hashes. The explicit immutable
selection contained only SVFLA-014; no other title was processed. Temporary
ASR cleanup reported PASS; the configured temp root was empty afterward,
`/tmp` had no files over 100 MiB, `/var/tmp` had 35 GiB free, and 8.5 GiB RAM
was available. No recovery or second retry was performed.

## 2026-09-26 deterministic unsafe audio timeline rollout semantics

Added `ASRAudioUnsafeTimelineError`, a narrow subtype of
`ASRAudioValidationError`. The audio canonicalizer raises it only for
deterministic source PTS invariants that make baseline timestamps unsafe:
duplicate/backward raw PTS, a per-frame correction beyond one decoded frame,
or peak signed net drift beyond the existing three-frame bound. The bound,
silence handling, and timestamp correction behavior are unchanged.

Stage11 lets this exception propagate from baseline transcription. Baseline
artifact persistence happens only after transcription returns, so this outcome
creates no baseline artifact and stops before external subtitle lookup or
alignment, targeted evidence, translation, or CLEAN materialization. External
subtitle evidence cannot bypass the unsafe baseline timeline.

Stage12 records the typed outcome as `RUNNING -> UNRESOLVED`, reason
`STAGE12_UNSAFE_AUDIO_TIMELINE`, with `stage11_outcome=UNSAFE_AUDIO_TIMELINE`.
It does not publish or query Jellyfin; batch processing can continue with the
next selected title. UNRESOLVED has no retry transition. Other
`ASRAudioValidationError` and `ASRAudioError` cases remain on their existing
retryable title path; the change does not make all audio validation errors
terminal.

Typed source-read (`ASRSourceError`), Whisper transport/protocol
(`ASRWhisperError`), and Stage11 deployment transport failures are title-scoped
`FAILED_RETRYABLE` outcomes. Unclassified deployment failures and unexpected
programming exceptions remain systemic. Existing typed worker timeout and
pending-artifact retry behavior is unchanged.

Audio, Stage11 controller, Stage12 batch, explicit retry, bulk runner, rollout,
deployment, ASR source, Whisper, and full-title transcriber smokes passed under
`/opt/stage11-stt-venv/bin/python`; compile and `git diff --check` passed. No
SVFLA-014 retry or production state change was performed. It remains
`FAILED_RETRYABLE`, sequence 3, with rollout counts
`PUBLISHED=158`, `FAILED_RETRYABLE=13`, `RUNNING=0`, `UNRESOLVED=2`. A later
authorized retry against the same unsafe source will resolve to UNRESOLVED
under this code. No title-specific branch or media repair was added.

## 2026-09-26 NHDTC-250 explicit retry production canary

At expected production HEAD
`ec021dfe356e6b9bd299764dc0bece5fcf3302a7`, the single-title explicit retry
passed the production interpreter, exact source identity, expected sequence,
and zero-active-title preflights. NHDTC-250 transitioned
`FAILED_RETRYABLE -> RUNNING`, sequence `7 -> 8`. The 6,618,791,523-byte
source copied to the configured temporary ASR root and full-title audio
processing completed through end-of-audio; every processed chunk's ASR call
returned normally and the aggregate had zero segments. Stage11 raised the
typed `FullTitleASRNoSpeechError`; this was not a systemic failure.

Stage12 recorded `RUNNING -> UNRESOLVED`, sequence `8 -> 9`, reason
`STAGE12_BASELINE_ASR_NO_SPEECH`, with `stage11_outcome=NO_SPEECH` and
`error_type=FullTitleASRNoSpeechError`. Final counts are `PUBLISHED=158`,
`FAILED_RETRYABLE=13`, `RUNNING=0`, `UNRESOLVED=2`. No baseline/report
artifact was created; publication and Jellyfin were not run. The retry
selected exactly one title, and the rollout event log has zero other-title
events since its start.

ASR temporary cleanup reported PASS and the production ASR temp root was
empty afterward. `/tmp` usage was 78 MiB (1%); available RAM was 8.5 GiB.
The retry process had exited, with no follow-up recovery or retry performed.

## 2026-09-26 Full-title ASR no-speech semantics and human ground truth

The five bounded NHDTC-250 targeted direct-Whisper audio clips were reviewed
by a human against the source. All five contain no human conversation;
non-speech vocalizations such as groans are present. The targeted segments are
therefore hallucinated/non-speech transcriptions, not speech evidence. One
segment had apparently favorable metrics (`avg_logprob=-0.063856`,
`no_speech_prob=0.160400`) despite having no speech. Numeric-only confidence
gates are not a safe production fix. Do not add non-VAD Whisper fallback when
VAD returns zero, and do not lower/loosen VAD thresholds.

Generic Stage11 policy: a full-title run that successfully decodes and submits
at least one audio chunk, completes all Whisper calls without transport or
protocol errors, and aggregates zero validated speech segments is a typed
`FullTitleASRNoSpeechError` outcome. An empty decoded-chunk stream remains a
contract/source failure. Decode, source transfer, worker, network, and
protocol errors retain their existing error paths. ASR result/artifact
non-empty validators stay strict.

Stage11 requires a non-empty baseline ASR result before it persists the
baseline, checks external JA subtitles, aligns evidence, or enters semantic
translation/review. External JA alignment also requires that ASR result, so
there is no safe existing continuation when baseline ASR has zero segments.
With an external JA subtitle present, Stage11 stops before querying it; with
one absent, it stops at the same boundary. Stage12 records this typed outcome
as terminal `UNRESOLVED` (`stage11_result=NO_SPEECH`, reason
`STAGE12_BASELINE_ASR_NO_SPEECH`), skips publication/Jellyfin, and continues
other titles in the batch. Repeating the same full-title inference is not
useful; no-speech is not `FAILED_RETRYABLE`. Real source/decode/transport/
worker/protocol failures keep their existing title/systemic classification.

## 2026-09-24 Targeted ASR numeric-only diagnostic contract

Added the explicit VM122 endpoint
`/v1/asr/transcribe-targeted-diagnostic` and
`RemoteFasterWhisperASR.transcribe_targeted_chunk_diagnostics()`. It runs the
existing whole-window, no-VAD targeted inference with unchanged model options.
The separate strict response carries only segment timestamps,
`avg_logprob`, `no_speech_prob`, `compression_ratio`, and `temperature`, plus
bounded request identity/count fields. It cannot carry transcript, word, or
token fields. The existing targeted endpoint and response schema are
unchanged; existing callers do not opt in and continue using the original
decoder.

The worker/remote protocol smokes verify unchanged normal targeted responses,
numeric-only diagnostics, and fail-closed rejection of text-bearing,
non-finite, and count-inconsistent diagnostic responses. GPU worker, remote
ASR, targeted second-evidence, Stage11 controller, compile, and `git diff
--check` passed under `/opt/stage11-stt-venv/bin/python`. The implementation
was committed and pushed as `6654fb6b018a25faa2cf0517ef3ebd5542ea3a74`.

VM122's previous worker and remote module hashes were
`ddb39a490d0a44a04d72b51293dea541dc7be4ab212b083fa5b16b336358f927` and
`e3fabce4890b14b4c006a2f67f7a12895d3af0b4ae8e6dc32a0a9735d3dd67b0`.
After exact old-hash checks, the modules were atomically replaced with
`a8df232ba220ae15d736137545e90f3c3bae7cb2432e5cc062688c76ad58e619` and
`0c68f7a7ed28da08cb3bd353e5f32daccd018cbb592e61d79678800ae579bfe8`.
The existing worker launcher and environment were retained; PID 97869 logged
`WORKER_READY`, owns port 8091, and serves both targeted routes. A valid legacy
targeted request using the original NHDTC-250 30–90-second PCM returned one
segment. Both old and new routes also rejected an empty invalid request with
HTTP 413. The numeric endpoint returned four bounded responses: three
NHDTC-250 windows and the FC2-PPV-4575470 control. No transcript text was
printed or saved.

All four full-decode PCM SHA-256 values matched the previously verified
windows exactly. NHDTC-250 segments (start/end are source milliseconds) were:

| Window (s) | Segment | Start–end (ms) | avg_logprob | no_speech_prob | compression_ratio | temperature |
|---|---:|---:|---:|---:|---:|---:|
| 30–90 | 1 | 88,940–89,980 | -0.664063 | 0.845703 | 0.857143 | 0 |
| 5,550–5,610 | 1 | 5,550,000–5,556,000 | -0.805990 | 0.821777 | 0.700000 | 0 |
| 5,550–5,610 | 2 | 5,583,020–5,596,780 | -0.063856 | 0.160400 | 0.700000 | 0 |
| 10,920–10,980 | 1 | 10,925,060–10,932,400 | -0.670573 | 0.742676 | 0.700000 | 0 |
| 10,920–10,980 | 2 | 10,956,880–10,979,980 | -0.580078 | 0.177124 | 0.600000 | 0 |

The FC2-PPV-4575470 30–90-second control returned 23 segments. Its numeric
score clusters were: segments 1–10 `avg_logprob=-0.283995`,
`no_speech_prob=0.386719`, `compression_ratio=1.656827`; segments 11–22
`-0.296944`, `0.005554`, `3.726141`; segment 23 `-0.216688`, `0.007515`,
`1.000000`. Temperature was 0 for all 23. NHDTC-250 therefore has a mixed
confidence profile: three segments have high no-speech probability and weaker
log probability, while two are materially better. This is **C**; the bounded
scores do not by themselves establish whether the weak segments are
hallucinations. Any later targeted-evidence fallback needs a generic,
validated confidence gate before it is trusted.

Both per-request source copies were on `/var/tmp` ext4, used one at a time,
and were removed successfully. `/tmp` remained 78 MiB; local available RAM was
8.4 GiB. VM122 returned to 3.9 GiB available RAM and 3.4 GiB free GPU memory;
the worker remained healthy. A read-only rollout query still showed
NHDTC-250 `FAILED_RETRYABLE`, sequence 7, with counts
`PUBLISHED=158`, `FAILED_RETRYABLE=14`, `RUNNING=0`, `UNRESOLVED=1`.
No rollout, publication, Stage11 controller, NAS, or Jellyfin writes occurred.

## 2026-09-24 NHDTC-250 full-title ASR empty result and recovery

At clean production HEAD `6e263d5dc35267a143b1cbeb6ff978d9b55fdcda`,
NHDTC-250's explicit retry reached EOF after full-media decode,
sample-clock canonicalization and source-end validation passed. The
transcriber then raised `FullTitleASRError: full-title ASR produced no speech
segments` at `teddy_discovery_asr_transcriber.py:420` because the validated
aggregate was empty. The iterator uses 600-second chunks. The preceding
read-only full replay recorded 178,315,129 output samples, yielding 19 chunks
(18 full chunks and a final partial chunk); the transcriber calls the remote
adapter once for each chunk and completed the loop before raising.

The production adapter returns decoded remote segments directly, and local
segment validation returns the tuple unchanged or raises; it does not filter
segments. Remote transport, HTTP and response-protocol errors also raise and
are not converted to empty success. Therefore this execution is classified
**A1 at the application boundary**: all 19 calls completed with zero segments
in aggregate (raw 0, accepted 0, rejected 0). The remote worker can return an
HTTP 200 response with `segments=[]` when VAD finds no regions. VM122's worker
log contains only its Sep 10 startup line; success requests are not logged, and
there is no per-request response/VAD count for this run. Its logs therefore do
not independently confirm each response or whether the audio was actually
silent. Existing PUBLISHED artifacts using the same large-v3 engine contain
275 segments for `FC2-PPV-4575470` and 404 for `SIRO-4448`; no transcript text
was copied into this note. NHDTC-250 produced no baseline artifact, and the
failure occurred before publication/Jellyfin.

Minimum generic diagnostics for a future run: chunk count, remote call count,
successful remote call count, raw/accepted/rejected segment counts, and the
first/last accepted timestamps. Keep transcript and subtitle text out of logs;
do not change systemic/title-local classification based on this incident.

The official `--mode recover-retry` path revalidated the Discovery/NAS source
identity and recovered only NHDTC-250, `RUNNING -> FAILED_RETRYABLE`, sequence
`6 -> 7`, reason `STAGE12_EXPLICIT_RETRY_CRASH_RECOVERY`, at
`2026-09-24T01:09:35.359448+00:00`. Counts are `PUBLISHED=158`,
`FAILED_RETRYABLE=14`, `RUNNING=0`, `UNRESOLVED=1`; the active-title set is
empty and the only new rollout event is NHDTC-250. No retry, Stage11, remote
ASR, publication, or Jellyfin write was performed during recovery. The
production ASR temp directory is empty, `/tmp` remains 78 MiB, `/var/tmp` is
the disk-backed `/dev/loop4` with 36 GiB available, and available RAM is 8.5
GiB.

## 2026-09-24 Stage12 production interpreter guard and explicit-retry recovery

Stage12 now fails closed before any PENDING bulk or explicit retry state
transition unless the process is launched by
`/opt/stage11-stt-venv/bin/python`, its resolved virtualenv prefix matches
`/opt/stage11-stt-venv`, and imports of local audio runtime dependencies
`numpy` and `av` succeed. The guard records `sys.executable`, its realpath,
prefix, and dependency results. Preflight-only CLI modes use the same guard.
This prevents another retry launched as system `python3` from reaching Stage11
or performing NAS/Jellyfin writes. The exact historical retry command below
now uses the production venv interpreter.

The generic `--mode recover-retry` path recovers only an explicitly selected
single stranded explicit retry from `RUNNING` to `FAILED_RETRYABLE`. It
requires the dedicated
`TEDDY_STAGE12_EXPLICIT_RETRY_RECOVERY_AUTHORIZED=YES_I_HAVE_REVIEWED_THE_SINGLE_TITLE`
authorization, one `--dvd-id`, expected sequence, exact clean HEAD, and the
singleton runner lock. It requires that title to be the only active
RUNNING/GENERATED title; verifies the Discovery/NAS path, source size and
mtime against rollout identity; checks artifact/publication absence and that
the latest event is exactly `FAILED_RETRYABLE -> RUNNING` with reason
`STAGE12_EXPLICIT_RETRY_START`; and uses a sequence plus previous-event CAS.
The audited recovery reason is
`STAGE12_EXPLICIT_RETRY_CRASH_RECOVERY`. Existing `recover_running()` remains
unchanged and still means `RUNNING -> PENDING` for ordinary crash recovery.
This recovery is an explicit operator action after a stranded retry; it does
not change Stage12's title-local/systemic exception classification or the
bounded exception-chain diagnostics added after the canary failure.

The recovery smoke covers authorization, exact selector, wrong status,
sequence, start event, source drift, other active titles, other-title state
invariance, the audited transition, and unchanged ordinary crash recovery.
Stage12 retry/batch/bulk/rollout/reconciliation, ASR audio/source/transcriber
and temp policy, Stage11 controller/deployment/live adapters, compile, and
`git diff --check` pass under the production venv.

After commit `c6ebe093d23578c118cb2b649fd44007d5ba1fa3` was pushed and its
clean HEAD/worktree rechecked, the authorized `recover-retry` path verified
the exact source identity/fingerprint and recovered NHDTC-250 only:
`RUNNING -> FAILED_RETRYABLE`, sequence `4 -> 5`, reason
`STAGE12_EXPLICIT_RETRY_CRASH_RECOVERY`, event time
`2026-09-23T23:51:04.881089+00:00`. Counts are now
`PUBLISHED=158`, `FAILED_RETRYABLE=14`, `RUNNING=0`, `UNRESOLVED=1`.
The only rollout event in the recovery interval was NHDTC-250's sequence-5
event; no other title state changed. No retry, Stage11, Remote ASR, NAS write,
or Jellyfin write ran. Do not run `--mode retry` without a separate operator
authorization.

Recovery command shape (fill `--expected-head` only with the reviewed clean
commit after push):

```sh
TEDDY_STAGE12_EXPLICIT_RETRY_RECOVERY_AUTHORIZED=YES_I_HAVE_REVIEWED_THE_SINGLE_TITLE \
  /opt/stage11-stt-venv/bin/python /opt/missav-pwa-subtitle-stage11/teddy_discovery_stage12_bulk_runner.py \
  --mode recover-retry --batch-size 1 --max-titles 1 \
  --dvd-id <exact-dvd-id> --expected-sequence <current-sequence> \
  --expected-head <exact-clean-authorized-HEAD>
```

## 2026-09-23 NHDTC-250 explicit retry systemic failure

At production canary HEAD `31db7b4da48e8841d5a33bde7c00ed1363c4c4b2`,
the explicitly authorized retry for `NHDTC-250` passed preflight, copied the
6,618,791,523-byte source into the configured disk-backed ASR temp root, then
stopped during Stage11 baseline ASR before a baseline ASR artifact was
created. Stage12 recorded `FAILED_RETRYABLE -> RUNNING`, sequence `3 -> 4`,
reason `STAGE12_EXPLICIT_RETRY_START`. The runner returned
`Stage12BatchSystemicError: unexpected Stage11 title execution exception`;
the existing saved heartbeat/CLI output did not preserve the original
low-level exception, so its type/message cannot be recovered from the
available production logs. Available evidence places the failure after source
copy and before baseline ASR artifact persistence. No publication or Jellyfin
stage was reached. Remote ASR request success cannot be determined from the
retained logs.

The request temp directory was cleaned. At the end of the canary,
`/tmp` usage was about 78 MiB, available RAM about 8.5 GiB, and no runner or
ffmpeg process remained. No other title state changed. The authoritative
rollout snapshot was `PUBLISHED=158`, `FAILED_RETRYABLE=13`, `RUNNING=1`,
`UNRESOLVED=1`, with `NHDTC-250=RUNNING`, sequence 4, reason
`STAGE12_EXPLICIT_RETRY_START`.

Diagnostic-only fix: Stage12 now persists a bounded exception-chain summary
with exception types and source locations at the systemic Stage11 wrapper.
Only controlled ASR exception messages are included; arbitrary exception
messages remain in-process to avoid storing subtitle text. The original
exception remains chained, systemic classification is unchanged, and this
does not broaden title-local failure isolation. Batch and explicit-retry
smokes confirm the cause is retained while an unexpected `RuntimeError`
remains systemic and the retry title is not falsely marked failed. These
smokes, Stage12 bulk/reconciliation/rollout, ASR source/temp policy, Stage11
controller, compile, and `git diff --check` passed. ASR audio and Stage11
deployment/live-adapter smokes could not run in this checkout because the
available Python environments lack `numpy`.

At this handoff update, no RUNNING recovery or retry has been performed.
Publication/Jellyfin writes and Remote ASR/Stage11 re-execution remain
unperformed. The only supported recovery API found in source is
`Stage12RolloutStateStore.recover_running(dvd_id)`, which transitions
`RUNNING -> PENDING` with `CRASH_RECOVERY`; it does not transition to
`FAILED_RETRYABLE`. Do not use it for this requested FAILED_RETRYABLE recovery.
There is no dedicated one-title `RUNNING -> FAILED_RETRYABLE` recovery path;
stop without changing rollout state unless a separately authorized supported
path is established.

## 2026-09-23 Stage12 Jellyfin contract preflight false positive

At source HEAD `8b6848d8913190a540fe4f14e9a2adfd228ffd7e`, an authorized
NHDTC-250 explicit retry command stopped in read-only preflight with
`Jellyfin recognition/fallback contract changed` and `LIVE_EXECUTED=NO`.
No rollout event/state, Remote ASR, Stage11, publication, or Jellyfin write
occurred. NHDTC-250 remains `FAILED_RETRYABLE`, sequence 3, reason
`STAGE12_TITLE_FAILURE`; rollout counts remain `PUBLISHED=158`,
`FAILED_RETRYABLE=14`, `UNRESOLVED=1`, with no active IDs.

Root cause: `contract_check()` in `teddy_discovery_stage12_bulk_runner.py`
required the `PlaybackInfo` request literal to appear in
`recognize_jellyfin_external_subtitle()`. Commit `d18dd5e` factored the exact
GET-only item/playback probe into `_jellyfin_external_subtitle_probe()` but
left that source-location predicate unchanged. The preflight therefore
reported a stale source-structure check, not a changed Jellyfin runtime
contract: the required PlaybackInfo route and exact path/language/external/
SubRip stream checks remain in the helper. Default item refresh, FullRefresh
fallback, the 42-attempt post-FullRefresh polling bound, and publication
reconciliation behavior are unchanged.

The generic fix keeps one shared `contract_check()` for PENDING and explicit
retry paths and checks the PlaybackInfo route in the helper that owns it.
Retry smoke now proves both the current contract passes and removal/mutation
of the helper route fails closed. Read-only explicit-retry and PENDING
preflight functions passed with the local dirty-worktree check isolated for
source-diff smoke; both reported `LIVE_EXECUTED=NO` and zero writes. Stage12
retry, batch, bulk-runner, reconciliation, rollout smokes, compile, and
`git diff --check` passed. The production retry remains unexecuted; perform it
only after reviewing this fix and authorizing a fresh single-title canary.

## 2026-09-22 SNOS-120 Stage12 timeout forensic and recovery

The timeout cleanup fix is committed as
`2f26fe54e6c83029df5c7c9b06ea9f6cacdd76b4`. After that fix, the
operator completed explicit crash recovery for SNOS-120: `RUNNING -> PENDING`,
reason `CRASH_RECOVERY`, transition sequence `2 -> 3`.

Current authoritative rollout state after recovery:

- `PUBLISHED=128`, `PENDING=28`, `FAILED_RETRYABLE=16`, `UNRESOLVED=1`
- `ACTIVE_IDS=[]`
- `SNOS-120=PENDING`, transition sequence 3, reason `CRASH_RECOVERY`
- Bulk runner has not been restarted; no NAS/Jellyfin production write occurred.
- CT120 has no orphan process for the SNOS-120 session.

The counts below describe the earlier forensic snapshot before recovery.

At authorized HEAD `1208ce107a4ecc919fa90b254365a8e447c2fdda`, the
production bulk runner stopped on SNOS-120 (session
`28586729-7f58-5b69-99de-194a0e081567`, 564 cues, 9 parts). Read-only
rollout DB evidence: `PUBLISHED=128`, `PENDING=27`, `FAILED_RETRYABLE=16`,
`RUNNING=1` (SNOS-120), `UNRESOLVED=1`; SNOS-120 transition sequence 2,
reason `STAGE12_BATCH_START`. No runner process was present on CT108. CT120
read-only process and runtime-marker checks found no process or marker for the
session at investigation time; no orphan cleanup was performed.

Root cause: `_invoke_hermes_part()` observed an inactivity timeout after
600 seconds without output, stopped local SSH, then called remote timeout
cleanup. The remote script emitted `REMOTE_TIMEOUT_CLEANUP_RESULT=CMDLINE_MISMATCH`
and exited 26, preserving its fail-closed PID identity check. That exit made
`_cleanup_timed_out_remote_hermes()` raise exactly `StatefulLiveRunnerError(
"remote Hermes timeout cleanup failed")`, with no explicit cause or context.
It happened before `_invoke_hermes_part()` could construct its typed
`StatefulLiveRunnerTimeoutError`. Its broad diagnostic handler printed
`HERMES_INVOCATION_TIMEOUT_REASON=NONE` and `RESULT=FAIL` because that handler
does not pass the already-set timeout reason. Stage12's exact title-exception
boundary does not classify generic `StatefulLiveRunnerError`, so it wrapped
the error in `Stage12BatchSystemicError("unexpected Stage11 title execution
exception")`. The production log does not contain a Python traceback; this
exception chain is established from its unique marker sequence and the
authorized source path.

Generic fix: once timeout is observed, catch only `StatefulLiveRunnerError`
from remote cleanup and retain it as the explicit `__cause__` of the primary
`StatefulLiveRunnerTimeoutError`. Emit the original timeout reason and
`RESULT=TIMEOUT`. The remote cmdline/CWD/session/PGID checks and fail-closed
behavior remain unchanged. Unexpected programming or transport exceptions
remain systemic.

Validation: stateful live runner smoke, timeout smoke (including stalled fake
process, successful remote process-group cleanup, cleanup failure and exact
CMDLINE_MISMATCH exception), Stage12 batch smoke (timeout isolation and
programmer/systemic retention), Stage12 bulk runner smoke, Python compile,
and `git diff --check` all passed. No production Hermes retry, DB write,
`recover_running()`, NAS/Jellyfin write, bulk restart, or remote kill occurred.

Operator next action: review the recovered `PENDING` state and the committed
timeout fix before any separately authorized bulk restart. Do not recover
SNOS-120 again.

> Canonical handoff for the next chat/session.  Read this file first and continue from here rather than reconstructing Stage11/Stage12 from old chat history.
>
> Last refreshed for chat handoff: **2026-09-23 KST**

## 0. 2026-09-20 HMN-899 Stage12 systemic-stop forensic and fix

The root-cause fix is committed as
`e33dc36e83d03e863aafcebc1017cab089107a96`. After that forensic session,
the operator completed the explicit crash recovery for `HMN-899`:
`RUNNING -> PENDING`, reason `CRASH_RECOVERY`, transition sequence `2 -> 3`.
There are now no active rollout IDs. The bulk runner has not been restarted,
and no NAS or Jellyfin production write occurred during recovery.

Current authoritative rollout state after recovery:

- `PUBLISHED=65`, `PENDING=102`, `FAILED_RETRYABLE=5`, `UNRESOLVED=1`
- `ACTIVE_IDS=[]`
- `HMN-899=PENDING`, transition sequence 3, reason `CRASH_RECOVERY`
- bulk runner not restarted

Authoritative read-only state at investigation time:

- `PUBLISHED=65`, `PENDING=101`, `FAILED_RETRYABLE=5`, `RUNNING=1`,
  `UNRESOLVED=1`
- `HMN-899` rollout source: `HMN/HMN-899/HMN-899.mp4`, size
  `3847055679`, mtime_ns `1788055221873611116`
- exact NAS `lstat`, obtained through
  `teddy_discovery_stage12_rollout.build_nas_preflight_filesystem`, matched all
  three identities and confirmed a regular file

A bounded `/tmp` forensic reproduction copied the exact canonical source,
verified the copied snapshot, and requested only the first production-shaped
600-second audio chunk. Source copy succeeded in about 30 seconds. Audio decode
then raised exactly:

`teddy_discovery_asr_audio.ASRAudioValidationError: audio frame timestamp has an unsafe discontinuity`

The exception had no `__cause__` and no unsuppressed `__context__`; that single
exception is the complete chain. It occurred in `_validate_frame_timeline()`
while advancing `iter_audio_chunks()`, before the first chunk was yielded, so
the Remote ASR HTTP boundary was never called.

Root cause of the bulk-wide stop was a Stage12 typed-boundary omission.
`FullTitleASRTranscriber` deliberately preserves `ASRAudioError` from its audio
iterator, but `Stage12BatchRunner._is_title_exception()` did not recognize that
typed operational media failure. `_run_one()` consequently wrapped it as
`Stage12BatchSystemicError("unexpected Stage11 title execution exception")` and
stopped the immutable batch while leaving the already-transitioned title
`RUNNING`.

The minimal generic fix adds only the `ASRAudioError` hierarchy to the Stage12
title-exception tuple. It does not catch all `Exception` or all `ASRError`, does
not weaken audio validation, and has no DVD/title-specific condition. A new
Stage12 batch regression proves that the exact `ASRAudioValidationError` is
recorded as `FAILED_RETRYABLE` and the next selected title proceeds; existing
tests continue to prove unrelated `RuntimeError`, generic live-runner,
deployment, and explicit systemic failures stop the batch.

Validation passed:

- Python compile for the changed batch module and smoke
- Stage11 ASR source, audio, Remote ASR, and full-title transcriber smokes
- Stage11 live-adapters and controller smokes
- Stage12 batch and bulk-runner smokes
- `git diff --check`

Operator next action: restart the bulk runner under normal authorization. The
stale `HMN-899` state has already been explicitly recovered; do not run crash
recovery for it again.

## 1. Immediate Goal

The next session has three ordered goals:

1. **Resolve the current `EBWH-350` Stage12 failure generically and safely.**
2. **Finish Stage12 holdings subtitle rollout and formally close Stage12.**
3. **Start Stage13 — Downloader NAS Library File Manager** using the already-built Discovery inventory rather than broad NAS scans.

Do not start Stage13 implementation until Stage12 is formally reconciled/closed, except for read-only planning if needed.

---

## 2. Overall Project Status

- Stage0–10: **CLOSED / PASS**
- Stage11: **CLOSED / PASS**
- R6: **CLOSED / PASS**
- Stage12: **ACTIVE** — holdings Korean-subtitle rollout / operations / hardening
- Stage13: **NOT STARTED** — scope frozen in this handoff for later implementation

Stage11 must **not** be redesigned or reopened just to solve rollout failures. Stage12 owns durable rollout state, publication, failure isolation, NAS placement, and Jellyfin recognition.

The Stage11 controller remains publication-free (`publication_performed=false`). Stage12 publishes only after a valid Stage11 CLEAN result.

---

## 3. Repository / Canonical Paths

Repository:

- GitHub: `ssikgun/missav-dlp-web`
- working tree on CT108: `/opt/missav-pwa-subtitle-stage11`
- branch: `teddy-subtitle-stage11`
- Git common dir: `/opt/missav-pwa-src/.git`
- canonical handoff: `docs/handoff/missav-dlp-web/CURRENT_HANDOFF.md`

Source-code HEAD immediately before this handoff-only refresh:

- `425276ea0b3252435fb19634c6ab864ba7a544a4`
- commit message: `Add activity-aware Hermes timeout`

Because this canonical handoff may be committed through GitHub directly, the CT108 worktree may be one handoff-only commit behind `origin/teddy-subtitle-stage11`. At the beginning of the next session, **fetch and fast-forward only** before making source edits; do not reset or overwrite local work blindly.

Suggested synchronization on **root@downloader (CT108)**:

```bash
cd /opt/missav-pwa-subtitle-stage11
git status --short
git fetch origin teddy-subtitle-stage11
git merge --ff-only FETCH_HEAD
git status --short
```

If the worktree is not clean or fast-forward fails, stop and inspect before doing anything else.

---

## 4. Infrastructure / Server Map

These are the servers directly involved in Stage11–13.

| Role | Host / IP | Important details |
|---|---|---|
| Downloader / Stage12 controller | **CT108 `downloader` — `192.168.1.155`** | repo/worktree `/opt/missav-pwa-subtitle-stage11`; production `/opt/missav-dlp-web`; Python `/opt/stage11-stt-venv/bin/python` |
| GPU ASR | **VM122 `local-llm` — `192.168.1.134`** | RTX 3060 12GB; ASR worker port `8091`; `/v1/asr/transcribe`, `/v1/asr/transcribe-targeted`; large-v3 CUDA/float16 |
| Hermes semantic worker | **CT120 `hermes-lxc-slack` — `192.168.1.230`** | Hermes binary `/home/teddy/.local/bin/hermes`; subtitle profile `/home/teddy/.hermes/profiles/subtitle-translator` |
| Synology NAS | **`192.168.1.201`** | managed media root `/volume1/video/video2/JAV`; user `ssikgun`; publication must be exact-path/bounded |
| Jellyfin | **`192.168.1.205:8096`** | external Korean SRT recognition; use normal item/library refresh only; direct Jellyfin DB writes forbidden |

CT108 → CT120 production SSH identity:

- user: `teddy`
- key: `/root/.ssh/id_ed25519_stage11_hermes`
- known_hosts: `/root/.ssh/known_hosts_stage11_hermes`

CT108 → NAS publication identity:

- key: `/opt/missav-dlp-web/teddy-nas-transfer/id_ed25519`
- known_hosts: `/opt/missav-dlp-web/teddy-nas-transfer/known_hosts`
- private key mode `0600`
- known_hosts mode `0644` is accepted and working; do not chmod it merely for a temporary check.

Stage12 data:

- Discovery DB: `/opt/missav-dlp-web/discovery/teddy-discovery.sqlite3`
- Stage12 rollout DB: `/opt/missav-dlp-web/discovery/stage12-rollout-state.sqlite3`
- rollout writer lock: `/opt/missav-dlp-web/discovery/stage12-rollout-state.sqlite3.lock`
- SubtitleCat-only Gluetun proxy: `http://127.0.0.1:58888`

---

## 5. Frozen Architecture / Safety Policy

Generic title flow:

`canonical holding → baseline ASR → external JA attempt → safe HYBRID else ASR_ONLY → source-quality → targeted evidence when required → stateful semantic translation/review → deterministic CLEAN → mechanical report → Stage12 publication`

Hard rules:

- no title-, DVD-ID-, cue-, or literal-text-specific production branching
- specific titles/cues may be used only as canary/audit/operator-selected evidence
- no broad recursive NAS scan
- no overwrite of existing canonical Korean subtitle
- no direct Jellyfin DB modification
- no automatic video modification
- fail closed on stale/corrupt/source-mismatched artifacts
- baseline/targeted ASR may be reused only through existing provenance checks
- uncertain subtitle content should generally be conservatively retained; the user accepts practical comprehension rather than commercial-grade translation
- do not weaken validators merely to force a title through

User-approved quality bar:

- understandable Korean subtitles are the goal
- awkward wording / some Whisper hallucination may remain
- suspected phrases such as `시청해 주셔서 감사합니다` are not automatically deleted without evidence
- uncertain KEEP is preferred to false deletion

---

## 6. Current Stage12 Rollout State

Authoritative inventory originally contained **173 holdings**:

- 172 eligible for canonical KO subtitle
- 1 unresolved: `JUR-750`

Current durable rollout counts after the latest `EBWH-350` canary failure remain:

- **PUBLISHED = 21**
- **FAILED_RETRYABLE = 3**
- **PENDING = 148**
- **UNRESOLVED = 1**
- **RUNNING = 0**
- **GENERATED = 0**

The remaining three `FAILED_RETRYABLE` titles are:

1. `DASS-884`
2. `DVDES-795`
3. `EBWH-350`

`JUR-750` is the separate `UNRESOLVED` title because a noncanonical sidecar already exists:

`JUR-750.R6B2-Clean.ko.srt`

Do not rename/delete/overwrite that automatically. Resolve it explicitly near Stage12 closure.

---

## 7. Activity-aware Hermes Timeout — Frozen Candidate

Commit:

- `425276ea0b3252435fb19634c6ab864ba7a544a4`

Current production candidate behavior:

- semantic policy default: `stage11-stateful-cue64-v1`
- model-input normalization: `stage11-model-input=repeat-v2`
- model validation attempts: `2`
- inactivity timeout: **600 seconds**
- **any stdout or stderr bytes reset the inactivity deadline**
- child output is forwarded/flushed live to the caller log
- absolute timeout: **3600 seconds**
- absolute timeout never resets
- timeout reason is explicit: `INACTIVITY_TIMEOUT` or `ABSOLUTE_TIMEOUT`
- timeout diagnostics include configured limits, invocation elapsed time, and seconds since last output activity
- promoted semantic parts are preserved on timeout
- no adaptive 16/64/128 fallback

Direct CT108 validation before the live canary passed:

- `git diff --check`
- `py_compile`
- activity-aware timeout smoke: 19 PASS / 0 FAIL
- retry smoke: 27 PASS / 0 FAIL
- live-runner contract smoke: 16 PASS / 0 FAIL
- stateful policy smoke: 17 PASS / 0 FAIL
- Stage12 batch smoke
- Stage11 live-adapters smoke

Important limitation:

The latest `EBWH-350` live canary confirmed the new timeout wiring in the real path, but it **did not directly exercise an active invocation continuing beyond 600 seconds**. All completed calls in that canary were below 600 seconds. Therefore the implementation is strongly smoke-tested and live-wired, but the exact `>600s while still producing output` behavior is not yet directly demonstrated by a production title.

`DASS-884` is a likely natural live case for that later because its previous failure was at part 28 after a hard 600-second wall-clock timeout.

---

## 8. EBWH-350 — CURRENT BLOCKER

### 8.1 Latest canary identity

Temporary runner:

- `/tmp/stage12-timeout-canary-ebwh350.py`

Canary namespace:

- `stage12-ebwh350-timeout-canary-425276ea-v1`

Fresh semantic session:

- `276cbd34-db1e-58e6-b5b6-858815b99e37`

Title shape:

- `CUE_COUNT=925`
- `PART_COUNT=15`

Previous timed-out session that was intentionally not reused:

- `a79234c6-e9d3-5461-ba4d-19814931e39f`

### 8.2 Preflight incident and solution — SQLite `-shm` false positive

Initial direct preflight failed even though it was read-only:

- `production SQLite fingerprint changed during preflight read`
- `TITLE_STATE=UNKNOWN`
- NAS source/KO verification then failed downstream because the DB read was rejected

Root cause was proven directly:

- quiet two-second period: no DB metadata change
- every `_read_rollout_and_discovery()` call changed **only** `teddy-discovery.sqlite3-shm` `mtime_ns`
- the main DB, WAL, rollout DB did not change
- no SQL mutation was requested

SQLite read-only WAL access can update the transient SHM metadata. Therefore using SHM `mtime_ns` as durable mutation evidence caused a false positive.

Temporary canary fix:

- main DB + WAL continue to use strict fingerprinting
- SHM is checked only for stable structure/safety (`dev`, `ino`, `size`, mode/type); SHM `mtime_ns` is excluded
- no `immutable=1` shortcut was introduced

After that fix, direct preflight passed **18/18**:

- `HEAD_MATCH=YES`
- `WORKTREE_CLEAN=YES`
- `TITLE_STATE=FAILED_RETRYABLE`
- source snapshot PASS
- baseline ASR provenance PASS
- targeted provenance PASS
- CT120 / VM122 / NAS / Jellyfin connectivity PASS
- exact NAS KO absent
- remote task root absent and unprovisioned
- timeout wiring PASS
- production writes 0
- `READY_FOR_EBWH350_TIMEOUT_CANARY=YES`

This SHM handling was applied to the **temporary canary runner**. Before broad use, decide whether the same generic read-only fingerprint rule belongs in reusable tooling; do not blindly copy temp-runner code into production without smoke coverage.

### 8.3 Latest live canary result

Parts **1–9 were validated and promoted**.

At part 10:

- first Hermes invocation: **PASS**, ~`159.360673s`, timeout reason `NONE`
- validator: `INVALID_KO`
- retry occurred
- second Hermes invocation: **PASS**, ~`135.148759s`, timeout reason `NONE`
- validator: `INVALID_KO` again
- final semantic result: `SEMANTIC_OUTPUT_VALIDATION_RETRY_EXHAUSTED=10`

The rollout DB correctly transitioned `EBWH-350` back to:

- `FAILED_RETRYABLE`
- reason: `STAGE12_SEMANTIC_OUTPUT_VALIDATION_RETRY_EXHAUSTED`

No NAS publication or Jellyfin mutation occurred.

### 8.4 Critical cue evidence — `asr-000624`

Read-only forensic proved that cue `asr-000624` already contains a long repetition in the **authoritative source input**:

- authoritative `stt_ja` length: `223`
- content is essentially repeated `え?` tokens many times

The same long repeated source is present in `stage11-semantic-input.json`.

Hermes part-10 output translated that into a very long repeated Korean sequence such as repeated `어?`.

Follow-up forensic identified the exact edge case. The authoritative source contains 74 spaced `え?` tokens with a leading delimiter. The source-aware KO validator itself is behaving correctly: it rejects genuine model amplification and must remain unchanged. The gap was in `repeat-v1` model-input normalization, which handled compact contiguous repetition but did not recognize identical short units separated by bounded horizontal whitespace. Hermes therefore received the pathological 74-token model input and amplified it further.

Do **not** solve this by title hardcode or by disabling the repetition validator.

### 8.5 Separate temporary runner reporting bug

After the Stage12 logic had already transitioned the title back to `FAILED_RETRYABLE`, the temporary canary runner crashed while printing the title result:

`NameError: name '_session_reader' is not defined`

Location in the temp runner:

`_emit_title_result()` → `actual_session = _session_reader(result.dvd_id)`

This happened **after** the true semantic failure had already been recorded. The rollout DB was not left `RUNNING`.

Treat this as a **temporary canary/reporting harness bug unless production code proves otherwise**. Fix it before reusing this temp runner so later failures are reported cleanly.

### 8.6 EBWH-350 forensic resolved — `repeat-v2` ready for bounded live retry

The read-only forensic and generic correction are complete.

Confirmed root cause:

1. `asr-000624` authoritative raw `stt_ja` is length `223` and contains 74 repeated short tokens separated by spaces, with a leading delimiter;
2. `repeat-v1` did not normalize that shape because its model-input repetition scanner required contiguous repeated units;
3. the source-aware validator strips whitespace for source evidence but still evaluates the full source string, so the leading delimiter prevents whole-string periodic evidence;
4. Hermes received the pathological unbounded model input and produced an even larger Korean repetition;
5. the validator therefore correctly rejected the amplified KO. **The validator was not weakened.**

Generic fix implemented locally:

- model-input identity advanced to `stage11-model-input=repeat-v2`;
- identical short units separated by one identical, bounded horizontal-whitespace separator can now be reduced to two representative units;
- line boundaries are never crossed;
- ordinary Japanese and ambiguous Unicode remain unchanged/fail-closed;
- authoritative raw source objects remain byte-for-byte separate from the model-input projection;
- stale or duplicate `stage11-model-input=*` generation identities now fail closed instead of accumulating multiple identities;
- no title, cue, or literal production hardcode was added.

Focused verification completed:

- Python compile: PASS;
- model-input normalization smoke: `28 PASS / 0 FAIL`;
- stateful translator smoke: PASS;
- stateful parts smoke: `45 PASS / 0 FAIL`;
- stateful policy smoke: `17 PASS / 0 FAIL`;
- live runner smoke: `16 PASS / 0 FAIL`;
- retry smoke: PASS;
- activity-aware timeout smoke: PASS;
- `git diff --check`: PASS.

Source-shaped forensic verification also passed:

- raw length remains `223`;
- raw token count remains `74`;
- model-input token count becomes `2`;
- projected model text is `- え? え?`;
- generation key contains `stage11-model-input=repeat-v2`;
- bound session identity differs from the old unbound session.

No Hermes live call, NAS publication, Jellyfin mutation, or production DB write was performed during this fix.

**Next action:** fix the separate temporary EBWH canary `_session_reader` reporting bug, ensure the retry uses a fresh `repeat-v2` semantic session rather than the old `repeat-v1` session, then run one bounded `EBWH-350` recovery canary with the existing fixed64 / inactivity-600 / absolute-3600 / attempts-2 safety contract.

---

## 9. Other Remaining Stage12 Failures

### DASS-884

Current known history:

- 1868 cues / 30 parts
- prior fixed64 recovery promoted parts 1–27
- part 28 hit the old hard wall-clock `600s` timeout
- remains `FAILED_RETRYABLE`
- no NAS/Jellyfin operation was performed for the failed attempt

After `EBWH-350` is resolved, use `DASS-884` as a bounded recovery candidate and observe whether the new activity-aware timeout naturally allows a still-active invocation to continue beyond 600 seconds. Do not claim success unless the live evidence actually crosses 600 seconds while output activity continues.

### DVDES-795

Prior failure was **not a timeout**:

- 1594 cues / 25 parts
- parts 1–4 promoted
- part 5 Hermes returned PASS and valid-looking output, but the remote pending artifact was missing
- generic `StatefulLiveRunnerError` was accidentally treated as systemic

Generic fix already frozen before the timeout work:

- specific `StatefulLiveRunnerPendingArtifactError`
- remote missing pending mapped explicitly
- only that specific missing-pending exception is title-level retryable
- other remote read/safety errors remain systemic
- promoted parts remain preserved

Commit containing that fix before the timeout commit:

- `0e9102bdc599e33e78c1534171157e250263b191`

It still needs one live bounded retry to prove the fix in production.

---

## 10. Important Past Incidents / Known Solutions

### Codex could edit files but could not Git commit

Symptom:

`git add` failed creating:

`/opt/missav-pwa-src/.git/worktrees/missav-pwa-subtitle-stage11/index.lock`

with `Read-only file system`.

Meaning:

- Codex sandbox could modify authorized worktree files but could not write the shared Git metadata.
- This was **not** evidence that CT108 Git itself was broken.

Solution:

- perform commit/push directly from **root@downloader (CT108)** after validating exact modified-file set and `git diff --check`.
- direct commit/push succeeded for the timeout work.

### Old Hermes timeout behavior

Old implementation used wall-clock `subprocess.run(..., timeout=600)`.

Observed historical failures:

- `DASS-884` part 28: ~600.000880 seconds
- `EBWH-350` old part 10: ~600.001017 seconds

Reasoning text existed before timeout, proving output had occurred, but old logs did not timestamp every chunk; they could not prove activity continued right up to second 600.

Solution:

- activity-aware `Popen`/selector runner now resets inactivity timer on stdout/stderr bytes and has independent absolute cap.

### DVDES-795 missing pending artifact

Root cause and solution are described above. Never broaden all `StatefulLiveRunnerError` to title-local; cleanup/safety/systemic errors must remain systemic.

### Source-aware repetition / model amplification history

The pipeline previously saw genuine model-amplified repetition as well as source-grounded repetition false positives. Generic source-aware handling remains in place. The original `repeat-v1` model-input normalization has now been superseded by separator-aware `repeat-v2`, while the validator remains fail-closed against genuine model amplification.

Do not regress to “long repeated text = delete/reject” without considering source evidence.

### CT108 memory incident during early CP6

An earlier CT108 SSH/unresponsiveness incident was memory/swap + I/O reclaim pressure, not VM122 ASR CPU.

Current CT108 allocation accepted during the project:

- memory: 10 GB
- swap: 1 GB

Browser/Selkies/Docker mixed workload contributed. `/dev/shm` was not the root cause.

---

## 11. Stage12 — Exact Remaining Work Order

Do these in order, one bounded checkpoint at a time.

### S12-1 — Resolve EBWH-350 generic `INVALID_KO`

- read-only validator/normalization forensic
- identify exact generic root cause
- implement generic source-aware fix
- smoke/regression tests
- fix temp canary `_session_reader` reporting defect
- run one bounded EBWH-350 recovery canary
- require full Stage11 PASS before publication
- verify exact NAS canonical KO and Jellyfin recognition

### S12-2 — Recover DVDES-795

- preflight current source/NAS/state
- exercise already-frozen missing-pending-artifact fix
- isolate failure if another issue occurs
- publish/Jellyfin only after full PASS

### S12-3 — Recover DASS-884

- preflight current source/NAS/state
- bounded fixed64/repeat-v2 recovery
- observe activity-aware timeout behavior
- preserve promoted parts according to current contract
- publish/Jellyfin only after full PASS

### S12-4 — Reconcile the three failure titles

Expected target before broad rollout:

- no `RUNNING` or `GENERATED` orphan
- each of the three is either `PUBLISHED` or an explicit still-visible failure with correct provenance
- do not silently hide failures

### S12-5 — Roll remaining `PENDING=148`

Use bounded serial rollout with durable resume/failure isolation.

Requirements:

- fixed64 default
- repeat-v2 normalization
- activity-aware Hermes timeout
- existing validators unchanged except evidence-backed generic fixes made above
- exact NAS KO check before title execution/publication
- existing KO protected
- baseline/targeted artifacts reused only through provenance checks
- each failed title isolated; batch continues according to the approved batch contract
- live log available while long jobs execute

Do not launch all 148 blindly before the three known failure classes have been reconciled.

### S12-6 — Resolve `JUR-750`

Explicit operator-safe decision for existing noncanonical:

`JUR-750.R6B2-Clean.ko.srt`

No automatic rename/delete/overwrite.

### S12-7 — Final Stage12 reconciliation and closure

Closure checklist:

- all 173 holdings accounted for
- `PENDING=0`
- `RUNNING=0`
- `GENERATED=0`
- every eligible title has an explicit terminal/accounted result
- valid published KO subtitles exist at exact canonical NAS paths
- existing KO files preserved
- Jellyfin recognizes published Korean external subtitles
- failures, if any are intentionally accepted, remain explicit and documented rather than hidden
- JUR-750 resolved explicitly
- canonical handoff updated
- commit/push clean
- Stage12 marker changed to **CLOSED / PASS** only when the closure criteria are actually met

---

## 12. Stage13 — Downloader NAS Library File Manager

Stage13 starts **after Stage12 formal closure**.

### Goal

Add a user-facing **File Management** section/tab to Downloader for the managed JAV library under:

`/volume1/video/video2/JAV`

It should behave like an operational library manager built on the existing Discovery inventory, not like a generic filesystem browser.

### Required capabilities

#### Inventory / browsing

- persistent inventory backed by existing Discovery data where possible
- no broad recursive NAS scan on every page load
- bounded reconcile/update mechanism
- expandable title/work rows similar to Discovery
- show useful metadata for each managed work
- screenshots/images may be shown/listed
- **video preview is not required**

#### Search

Search by at least:

- DVD-ID / product code
- title

Jellyfin search quality should also be improved so DVD-ID/product-code lookup is reliable rather than depending only on title text.

#### Korean subtitle status

KO subtitle state is a first-class field:

- canonical KO present / absent
- ideally valid / unresolved state when useful
- filter: KO present
- filter: KO absent

Reuse Stage12 canonical subtitle/path rules rather than inventing a conflicting second definition.

#### Sort

Support practical sorts including:

- download/addition date
- Korean subtitle state
- release date
- DVD-ID / product code
- title

#### Deletion

Deletion is destructive and must be implemented only after read-only inventory/browse behavior is proven.

Safety requirements:

- delete only one exact managed work/title at a time
- explicit user confirmation
- canonical root containment under `/volume1/video/video2/JAV`
- reject traversal
- reject symlink escape
- no broad wildcard/recursive delete outside the exact managed title directory
- fail closed on inventory/path identity mismatch
- update durable inventory only after filesystem result is verified
- trigger normal Jellyfin refresh/reconcile after deletion
- never modify Jellyfin DB directly

Before choosing delete semantics, inspect **Synology recycle-bin behavior** for this share and decide whether deletion should intentionally use or bypass recycle behavior. Do not assume.

### Suggested Stage13 implementation order

1. **Stage13 CP1 — read-only inventory contract**
   - map Discovery holding → exact NAS managed work path
   - verify metadata fields / KO state / screenshot enumeration contract
   - no filesystem mutation

2. **Stage13 CP2 — File Management UI shell**
   - browse, expand, search, filter, sort
   - read-only only

3. **Stage13 CP3 — bounded inventory reconcile/cache**
   - durable/updateable without broad page-load scans

4. **Stage13 CP4 — deletion preflight / safety contract**
   - exact title path
   - containment/symlink checks
   - confirmation model
   - Synology recycle behavior verified
   - dry-run only

5. **Stage13 CP5 — one-title deletion canary**
   - only with explicit user authorization
   - verify filesystem result + Discovery state + Jellyfin refresh

6. **Stage13 CP6 — operational hardening / closure**

Stage13 must reuse Discovery rather than creating an unrelated second library index unless a separate cache is technically required. If a cache is introduced, Discovery remains the authoritative logical inventory and reconciliation must be explicit.

---

## 13. Major Recent Commits / Milestones

Useful recent commits in chronological order:

- `7ae8d5e...` — Stage11/R6 closure
- `16346e8...` — Stage12 scope
- `86336ad...` — CP1 inventory
- `9e75621...` — CP2 rollout state
- `06c8bfa...` — CP3 NAS publication
- `c0baa59...` — CP4 Jellyfin recognition
- `6a1c801...` — CP5 3-title rollout/reconciliation
- `ac39754...` — alignment-limit safe fallback
- `cecefa11...` — bounded semantic retry/per-title isolation
- `9e9fde3f...` — Hermes timeout isolation
- `9363646f...` — CP6 closure handoff
- `b65ae36f...` — source-aware repeated cue fix
- `35b85adf...` — fixed64 rollout candidate
- `2264f8f0...` — fixed64 promoted as stateful default
- `0e4d64b9...` — pathological repetition normalization before Hermes
- `23c2f17c...` — orphan-state recovery
- `4021898c...` — normalized EROFV-387 recovery
- `0e9102bdc599e33e78c1534171157e250263b191` — missing pending-artifact typed recovery
- `425276ea0b3252435fb19634c6ab864ba7a544a4` — activity-aware Hermes timeout

Do not assume abbreviated SHAs are unique without `git rev-parse` when performing source changes.

---

## 14. Working / Reporting Rules for the Next Chat

The user prefers short, practical reporting.

For pasted terminal/Codex results:

- first visible token must be exactly one of: `PASS`, `FAIL`, `INCOMPLETE`
- explain the key meaning in simple Korean
- distinguish confirmed facts from inference / needs-checking
- give **exactly one next checkpoint**
- do not dump unnecessary theory/log repetition

Command discipline:

- always state execution location near command blocks (`root@downloader (CT108)`, `teddy@local-llm (VM122)`, `teddy@hermes-lxc-slack (CT120)`, etc.)
- one checkpoint at a time
- no blind retry
- for real long-running live commands, provide a **real-time log viewing command** (`tee`, `tail -f`, or a filtered watcher)
- do not use shell-killing patterns such as `exit`, naked `false`, `set -e`, `set -eu`, `set -euo pipefail`, `|| exit 1`, shell-replacing `exec`, or `kill $$`
- avoid broad NAS `find`, `os.walk`, `rglob`, or `du`; use exact/bounded paths

Implementation discipline:

- prefer Codex for bounded implementation/smoke/forensic work
- do not make Codex wait on long Hermes production runs
- long live Hermes jobs run directly from CT108 in background with observable logs
- important source changes require canonical handoff update and commit/push
- do not modify unrelated projects/files

---

## 15. First Checkpoint in the New Chat

The `EBWH-350` validator forensic and generic `repeat-v2` implementation are complete and smoke/regression tested.

Do **not** redo the validator investigation and do **not** weaken the validator.

The immediate next checkpoint is:

1. inspect/fix the temporary EBWH canary `_session_reader` reporting bug only;
2. verify that the bounded retry will create/use a fresh `repeat-v2` semantic session and will not reuse the old `repeat-v1` semantic session;
3. run one observable bounded `EBWH-350` recovery canary;
4. publish to NAS/Jellyfin only if the complete Stage11 result reaches valid CLEAN through the normal Stage12 publication path.

If the live recovery fails, keep the failure title-local as `FAILED_RETRYABLE` and inspect the new evidence before changing policy.

After `EBWH-350` is resolved, continue the existing Stage12 remaining-work order toward formal closure, then start Stage13.

## 2026-09-17 — EBWH-350 repeat-v2 live forensic + semantic repetition policy

### Status

- Stage12 remains **ACTIVE**.
- EBWH-350 repeat-v2 bounded live canary did **not publish** and remains `FAILED_RETRYABLE`.
- Parts 1–9 validated/promoted successfully.
- Part 10 ended at the controller with `INACTIVITY_TIMEOUT`.
- NAS publication: **NOT_RUN**
- Jellyfin refresh: **NOT_RUN**

### EBWH-350 repeat-v2 forensic result

The repeat-v2 model-input normalization itself is confirmed working correctly.

For the problematic source cue:

- authoritative/raw `stt_ja`: 74 spaced repetitions
- local semantic/model input: 2 representative repetitions
- remote CT120 semantic input: 2 representative repetitions
- Hermes part-10 output: 87 Korean repetitions

Therefore the remaining repetition failure is **not** a repeat-v2 projection/wiring failure.
Hermes semantically re-expanded a correctly bounded model input.

The existing output validator correctly rejected this kind of runaway result and was not weakened.

### Part-10 timeout / remote lifecycle finding

The part-10 remote pending artifact existed and was structurally complete before the controller timed out.

Observed:

- remote `semantic-part-0010.pending.json` mtime was about 42 seconds after part start
- JSON parsed successfully
- cue coverage: 64 / 64 unique, correct first/last cue IDs
- controller later reached the 600-second inactivity timeout
- CT120 still had the exact subtitle-translator shell/Hermes process alive after the CT108 controller had already returned

This proves a separate remote lifecycle bug:

- controller timeout can leave the remote Hermes task/process running
- manual forensic cleanup terminated the exact orphan task processes
- generic Hermes dashboard/gateway and unrelated Codex processes were not targeted

This orphan cleanup behavior is **not yet fixed in production source**.

### Generic semantic repetition policy added

A shared stateful semantic repetition instruction is now used by both:

1. the initial whole-title `STATEFUL_TRANSLATOR_QUERY`
2. every resumed deterministic part query built by the stateful controller

Policy is generic and title-independent:

- excessive non-semantic repetition such as fillers/interjections/non-lexical vocalizations should be compressed to a short natural representative expression
- meaningful repetition, emphasis, stuttering, chanting, rhythm, or other scene-relevant repetition should be preserved
- translated output must not increase repeated units beyond the current authorized model-input evidence
- a longer repetition must not be reconstructed from earlier session history or historical artifacts
- uncertain repetition is retained conservatively rather than deleted

No DVD ID, work-specific phrase, cue ID, or title-specific literal is embedded in production policy.

### Validation

- Python compile: **PASS**
- stateful translator smoke: **PASS**
- stateful controller smoke: **29 PASS / 0 FAIL**
- stateful live runner smoke: **16 PASS / 0 FAIL**
- `git diff --check`: **PASS**

### Next work

Next highest-priority checkpoint:

**Fix the generic CT120 remote-process lifecycle so a controller timeout terminates/reaps only the exact remote subtitle-translator task and cannot leave an orphan Hermes invocation.**

After that fix and regression smoke, run a fresh bounded EBWH-350 canary session using:

- repeat-v2 model input
- the new generic semantic repetition policy
- the fixed remote timeout cleanup path

Do not weaken semantic validators to force publication.

## 2026-09-17 — Remote Hermes timeout lifecycle cleanup

### Status

The CT120 orphan-Hermes timeout bug found during the EBWH-350 repeat-v2 canary is now fixed in production source.

Root cause:

- CT108 inactivity/absolute timeout stopped only the local SSH `Popen`
- the already-running CT120 `bash` / Hermes process could survive after SSH termination
- this was live-proven during the EBWH-350 part-10 timeout

### Fix

The stateful live runner now uses task-scoped runtime ownership markers:

- `.stage11-hermes-runtime.pid`
- `.stage11-hermes-runtime.meta`

Remote Hermes execution is started in its own process group with `setsid`.

On controller timeout, a second bounded SSH cleanup verifies all of the following before terminating anything:

- expected CT120 hostname
- exact remote task directory exists
- PID and metadata files exist and are valid
- metadata session ID exactly matches the current Stage11 session
- `/proc/<pid>/cwd` exactly matches the current remote task directory
- `/proc/<pid>/cmdline` identifies the subtitle-translator Hermes invocation
- exact `--resume <session_id>` is present
- process-group ID equals the recorded leader PID

Only after these checks does cleanup send TERM to the exact process group.
KILL is used only as a bounded fallback if that exact process remains alive.

No broad `pkill`, `killall`, or generic Hermes process scan is used.

Runtime marker files are removed after successful cleanup.
Existing semantic pending artifacts are not deleted by timeout cleanup.

### Validation

Synthetic end-to-end timeout lifecycle smoke: **PASS**

Confirmed:

- target timeout process group was terminated
- target process was reaped
- runtime PID/meta markers were removed
- unrelated concurrent Hermes process remained alive
- existing inactivity timeout classification still passes
- existing absolute timeout classification still passes
- activity-aware timeout behavior remains unchanged
- remote pending recovery contract remains unchanged
- `git diff --check`: **PASS**

### Next work

Run a fresh bounded EBWH-350 canary session using:

- repeat-v2 model-input normalization
- generic semantic repetition guard
- exact remote timeout lifecycle cleanup

Expected objective:

- verify the pathological source cue no longer expands in Korean output
- verify no CT120 orphan process remains if a timeout occurs
- publish nothing unless the existing semantic validators accept the result

## 2026-09-17 — EBWH-350 repeat-v2 production canary PASS

### Final result

EBWH-350 Stage12 recovery canary completed successfully.

Production result:

- Stage11 semantic translation: PASS
- total cues: 925
- total parts: 15
- all 15 parts validated and promoted
- NAS publication: PASS
- Jellyfin recognition: PASS
- final rollout state: `PUBLISHED`
- destination: `EBWH/EBWH-350/EBWH-350.ko.srt`

Final rollout counts:

- `PUBLISHED=22`
- `FAILED_RETRYABLE=2`
- `PENDING=148`
- `UNRESOLVED=1`

### Repetition regression proof

The previous failure occurred in part 10 around the pathological repeated cue.

With repeat-v2 plus the generic semantic repetition guard:

- the semantic input remained bounded
- Hermes did not regenerate the previous excessive repetition
- cue `asr-000624` produced Korean `어? 어?`
- part 10 passed current Stage11 validators
- validators were not weakened

This live run confirms the generic repetition policy works on the original failing production case.

### Timeout/orphan lifecycle proof

The live runner exited normally after the canary.

Post-run verification:

- local canary runner: exited
- `.stage11-hermes-runtime.pid`: absent
- `.stage11-hermes-runtime.meta`: absent

No stale CT120 runtime ownership marker remained.

The earlier timeout cleanup implementation had already passed synthetic exact-process-group cleanup validation.
This successful production run additionally confirms the normal-completion lifecycle leaves no runtime marker residue.

### Frozen EBWH-350 conclusion

EBWH-350 is closed as a successful Stage12 recovery case.

The validated production combination is:

- `stage11-model-input=repeat-v2`
- `stage11-stateful-cue64-v1`
- generic semantic repetition guard
- inactivity timeout: 600 seconds
- absolute timeout: 3600 seconds
- exact task/session-scoped remote Hermes lifecycle ownership
- existing Stage11 validators unchanged

### Remaining Stage12 failures

Two `FAILED_RETRYABLE` titles remain:

- DVDES-795
- DASS-884

EBWH-350 must not be retried again unless a new regression is discovered.

## 2026-09-17 — DVDES-795 production recovery PASS

### Final result

DVDES-795 Stage12 recovery completed successfully.

Production result:

- semantic session: fresh repeat-v2 session
- total cues: 1594
- total parts: 25
- all 25 parts validated and promoted
- Stage11 result: PASS
- NAS publication: PASS
- Jellyfin recognition: PASS
- final rollout state: `PUBLISHED`
- destination: `DVDES/DVDES-795/DVDES-795.ko.srt`

Final rollout counts:

- `PUBLISHED=23`
- `FAILED_RETRYABLE=1`
- `PENDING=148`
- `UNRESOLVED=1`

### Missing-pending regression proof

DVDES-795 previously failed after Hermes returned PASS for part 5 because the remote pending artifact was missing and the generic error path was treated as systemic.

The frozen generic fix introduced:

- `StatefulLiveRunnerPendingArtifactError`
- only the exact missing-pending condition is title-level retryable
- unrelated remote read/safety/systemic failures remain systemic
- previously promoted parts remain preserved

The production recovery passed the original failure boundary:

- part 5 validated successfully
- `PROMOTED_PART=5/25`
- execution continued through all 25 parts
- no validator weakening was required

This is the production proof for the missing-pending recovery contract.

### Current production policy

The successful recovery used:

- `stage11-model-input=repeat-v2`
- `stage11-stateful-cue64-v1`
- inactivity timeout: 600 seconds
- absolute timeout: 3600 seconds
- current Stage11 validators unchanged
- fresh semantic session; previous failed session was not reused

### Runtime cleanup verification

Post-run verification:

- local canary runner: exited
- `.stage11-hermes-runtime.pid`: absent
- `.stage11-hermes-runtime.meta`: absent

No runtime ownership marker remained on CT120 after successful completion.

### Remaining Stage12 failure

Only one `FAILED_RETRYABLE` title remains:

- `DASS-884`

`DVDES-795` must not be retried again unless a new regression is discovered.

## 2026-09-17 — DASS-884 production recovery PASS

### Final result

DASS-884 Stage12 recovery completed successfully.

Production result:

- fresh repeat-v2 semantic session
- total cues: 1868
- total parts: 30
- all 30 parts validated and promoted
- Stage11 result: PASS
- NAS publication: PASS
- Jellyfin recognition: PASS
- final rollout state: `PUBLISHED`
- destination: `DASS/DASS-884/DASS-884.ko.srt`

Final rollout counts:

- `PUBLISHED=24`
- `PENDING=148`
- `UNRESOLVED=1`
- `FAILED_RETRYABLE=0`

### Previous timeout recovery

The previous DASS-884 recovery used repeat-v1 with the old fixed 600-second wall-clock timeout.

That run:

- promoted through part 27/30
- requested part 28/30
- terminated at approximately 600.000880 seconds
- ended as `FAILED_RETRYABLE`

The successful recovery used the current production contract:

- `stage11-model-input=repeat-v2`
- `stage11-stateful-cue64-v1`
- inactivity timeout: 600 seconds
- absolute timeout: 3600 seconds
- current Stage11 validators unchanged
- fresh semantic session; previous failed session was not reused

Part 28 passed successfully in the new recovery and execution continued through part 30.

Note: this successful run proves recovery from the former part-28 failure, but it does not independently prove a >600-second live invocation surviving via activity reset because the successful part 28 completed below 600 seconds.

### Runtime cleanup verification

Post-run verification:

- local canary runner: exited
- `.stage11-hermes-runtime.pid`: absent
- `.stage11-hermes-runtime.meta`: absent

No runtime ownership marker remained on CT120 after successful completion.

### Stage12 current state

There are now no `FAILED_RETRYABLE` titles.

Remaining work:

- process the remaining `PENDING=148` titles
- resolve the single `UNRESOLVED=1` title separately
- the unresolved title is JUR-750 with its noncanonical KO sidecar condition

DASS-884 must not be retried again unless a new regression is discovered.

## 2026-09-17 — Pending5 malformed external JA fallback incident

### Incident

The first current-policy five-title Stage12 PENDING canary selected:

- EROFV-390
- EYAN-228
- FBOS-015
- FC2-PPV-4451371
- FC2-PPV-4551303

EROFV-390 completed successfully:

- route: `ASR_ONLY`
- Stage11: PASS
- NAS publication: PASS
- Jellyfin recognition: PASS
- final rollout state: `PUBLISHED`

The batch then claimed EYAN-228 as `RUNNING`.

Its external Japanese subtitle contained an invalid control character during
lexical alignment. `normalize_japanese_for_matching()` correctly raised
`AlignmentValidationError`, but the live external-JA adapter mapped only
`AlignmentLimitError` into `ExternalSubtitleValidationError`.

That validation error therefore escaped the intended external-subtitle
fallback boundary and Stage12 conservatively promoted the unexpected
exception to `Stage12BatchSystemicError`, stopping the serial batch.

### Generic fix

Production code now maps generic `AlignmentValidationError` from external-JA
alignment to `ExternalSubtitleValidationError`.

This preserves the existing controller contract:

malformed external JA -> external validation failure -> `ASR_ONLY`

The existing specialized `AlignmentLimitError` message remains unchanged.

No DVD-ID, title, cue, literal subtitle text, or work-specific production
condition was added.

Source-fix commit before this handoff update:

- `26b09202a87096726bfb1dd796a641c55b61d0b9`

Validation:

- alignment fallback smoke: PASS
- Stage11 live adapters smoke: PASS
- Stage11 controller smoke: PASS
- Stage12 batch smoke: PASS
- `git diff --check`: PASS

### Crash recovery

After the failed batch process had exited and all exact CT120 Hermes runtime
PID/meta markers were confirmed absent, EYAN-228 was recovered through the
existing official `Stage12RolloutStateStore.recover_running()` path:

`RUNNING -> PENDING`

Reason:

- `CRASH_RECOVERY`

EROFV-390 must not be rerun.

Current rollout counts after recovery:

- `PUBLISHED=25`
- `PENDING=147`
- `RUNNING=0`
- `UNRESOLVED=1`
- `FAILED_RETRYABLE=0`

### Next action

Resume only the four unfinished members of the original canary:

1. EYAN-228
2. FBOS-015
3. FC2-PPV-4451371
4. FC2-PPV-4551303

Use a fresh batch/runtime namespace and the current production contract:
cue64, repeat-v2, 600-second inactivity timeout, 3600-second absolute timeout,
retry count 2, and exact-process Hermes orphan cleanup.

## 2026-09-18 — Pending4 canary closure and Jellyfin FullRefresh fallback

### Pending4 canary final result

The four-title continuation canary ran on the current Stage11/Stage12
production contract:

- semantic policy: `stage11-stateful-cue64-v1`
- model input: `stage11-model-input=repeat-v2`
- inactivity timeout: 600 seconds
- absolute timeout: 3600 seconds
- model retries: 2
- exact-process Hermes orphan cleanup retained

Selected titles:

1. EYAN-228
2. FBOS-015
3. FC2-PPV-4451371
4. FC2-PPV-4551303

Final title states:

- EYAN-228: `PUBLISHED`
- FBOS-015: `PUBLISHED`
- FC2-PPV-4451371: `PUBLISHED`
- FC2-PPV-4551303: `PUBLISHED`

EYAN-228 confirmed the malformed-external-JA fallback fix in production:
the unsafe external Japanese candidate was rejected and the title continued
through `ASR_ONLY` instead of aborting the batch.

The canary also confirmed title-level isolation. FC2-PPV-4451371 encountered
a Jellyfin recognition failure after successful Stage11 generation and NAS
publication, but the serial batch continued and FC2-PPV-4551303 completed
successfully.

### FC2-PPV-4451371 Jellyfin recovery

For FC2-PPV-4451371:

- Stage11 result: PASS
- NAS publication: PASS
- durable CLEAN SHA-256:
  `c2e76532d5ba84b335815b1a7ca88a3e9a4300f1f4203e75e9709c08d2669fdb`
- NAS destination SHA matched the durable CLEAN artifact exactly
- Jellyfin Default item refresh did not discover the new external subtitle
- item-specific `MetadataRefreshMode=FullRefresh` discovered the exact
  external Korean SUBRIP stream
- official `Stage12RolloutStateStore.reconcile_published()` was used
- no controller rerun
- no translation rerun
- no NAS rewrite
- final state: `PUBLISHED`
- reconciliation reason: `PUBLICATION_RECONCILED`

### Generic Jellyfin production hardening

`teddy_discovery_stage12_batch.py` now retains the existing bounded
item-specific Default refresh first.

If the exact external Korean subtitle is still not visible after that polling
window, the same exact Jellyfin item receives one item-specific FullRefresh,
followed by the same bounded PlaybackInfo polling.

This is generic behavior:

- no DVD-ID-specific branch
- no title-specific path rule
- no subtitle-text-specific logic
- no library-wide refresh
- existing exact item/path/language/codec checks remain unchanged

Validation completed before handoff update:

- Python compile: PASS
- `teddy_discovery_stage12_batch_smoke.py`: PASS
- `teddy_discovery_stage12_rollout_smoke.py`: PASS
- `git diff --check`: PASS

### Current Stage12 rollout state

- PUBLISHED: `29`
- PENDING: `143`
- FAILED_RETRYABLE: `0`
- FAILED_TERMINAL: `0`
- RUNNING: `0`
- GENERATED: `0`
- UNRESOLVED: `1`

The one UNRESOLVED title remains JUR-750 and stays isolated from normal
PENDING rollout work.

### Next action

Resume Stage12 from the remaining ordinary `PENDING` titles under the current
generic production contract. Do not rerun already `PUBLISHED` titles.
Do not automatically include JUR-750 in normal PENDING processing.

## 2026-09-18 — Subtitle status mini-panel

### Goal

Expose Stage12 subtitle rollout status in the Downloader Settings page before
starting the remaining bulk subtitle rollout.

The panel is intentionally read-only and temporary in the Settings page.
It can later be moved to the future file-management page without changing
the status API contract.

### Implemented

New read-only endpoint:

- `GET /api/subtitles/status`

New components:

- `teddy_subtitle_status.py`
- `teddy_subtitle_status_smoke.py`
- `teddy_subtitle_status_ui_smoke.py`
- `templates/teddy-subtitle-status.css`
- `templates/teddy-subtitle-status.js`

Settings UI now displays:

- overall runner state
- current DVD ID
- current stage / part progress when heartbeat provides it
- PUBLISHED
- PENDING
- FAILED_RETRYABLE
- FAILED_TERMINAL
- UNRESOLVED
- last activity

The panel does not expose start/stop/retry controls.

### State sources

The status API reads the existing Stage12 rollout SQLite database read-only.

Production container contract:

- `TEDDY_SUBTITLE_STATE_PATH=/stage12/stage12-rollout-state.sqlite3`
- `TEDDY_SUBTITLE_HEARTBEAT_PATH=/stage12-runtime/status.json`

Production mounts:

- rollout DB: exact file, read-only
- heartbeat directory: read-only

The Downloader container never writes Stage12 rollout state or heartbeat.

### Runner-state contract

A remaining PENDING count does not mean the runner is active.

The UI distinguishes:

- `running`: fresh runner heartbeat says RUNNING
- `idle`: no live runner and no active rollout title
- `stale`: durable RUNNING/GENERATED state exists without a fresh heartbeat
- `attention`: retryable/terminal failures exist
- `error`: fresh runner heartbeat reports ERROR

Heartbeat freshness threshold is currently 120 seconds.

The upcoming bulk Stage12 runner must write the heartbeat atomically to:

`/opt/missav-dlp-web/discovery/stage12-runtime/status.json`

### Validation

Completed before deployment:

- Python compile: PASS
- subtitle status backend smoke: PASS
- subtitle status UI smoke: PASS
- existing Discovery UI shell regression: PASS
- `git diff --check`: PASS
- production compose validation: PASS

Current read-only rollout snapshot at implementation time:

- PUBLISHED: 29
- PENDING: 143
- FAILED_RETRYABLE: 0
- FAILED_TERMINAL: 0
- UNRESOLVED: 1
- runner status: idle

### Deployment state

Production compose was prepared with read-only Stage12 mounts and backed up
before modification.

The running production image has not yet been replaced.

The Docker workflow automatically builds on `teddy-custom` pushes only.
For this `teddy-subtitle-stage11` branch, use `workflow_dispatch` to build
the immutable `teddy-<commit SHA>` image. Do not promote the mutable
`teddy-custom` tag from this branch.

### Next action

Build the current `teddy-subtitle-stage11` commit through the existing
GitHub Actions workflow, pin the resulting immutable image in production,
verify `/api/subtitles/status` and the Settings mini-panel, then start the
remaining 143-title Stage12 production rollout with heartbeat reporting.

## 2026-09-18 — Stage12 bulk runner prepared

### Current production UI

The Downloader Settings subtitle-status mini-panel is deployed and verified.

Production web image:

- revision: `24f6a6c62058ea0ad4d0ec204b9c9ecc285c9de8`
- digest: `sha256:fb1e9c6dc655c3cd7044e8a8c1711414589e2c1695503e866fe178c3396e6b79`

The Stage12 rollout DB and heartbeat directory are mounted read-only inside
the Downloader container.

Current visible rollout state before bulk execution:

- PUBLISHED: 29
- PENDING: 143
- FAILED_RETRYABLE: 0
- FAILED_TERMINAL: 0
- UNRESOLVED: 1
- active RUNNING/GENERATED: 0

Dark-mode styling of the temporary Settings card is intentionally deferred
until the card is moved into the future file-management page.

### Formal Stage12 bulk runner

Added:

- `teddy_discovery_stage12_bulk_runner.py`
- `teddy_discovery_stage12_bulk_runner_smoke.py`

The runner reuses the existing production contracts rather than introducing
a new subtitle pipeline:

- deterministic eligible PENDING selection
- exact selected NAS inventory revalidation
- frozen Stage11 controller
- cue64 semantic policy
- repeat-v2 model input
- 600-second Hermes inactivity timeout
- 3600-second absolute timeout
- two validation attempts
- exact-process Hermes cleanup
- malformed external-JA fallback to ASR_ONLY
- serial Stage12 title isolation
- atomic no-overwrite publication
- exact Jellyfin external-KO recognition
- bounded Default-to-FullRefresh Jellyfin fallback

FAILED_RETRYABLE, FAILED_TERMINAL, PUBLISHED and UNRESOLVED titles are not
implicitly selected as normal bulk work.

No title/DVD-specific production branch is present.

### Heartbeat

The bulk runner writes an atomic heartbeat to:

`/opt/missav-dlp-web/discovery/stage12-runtime/status.json`

Heartbeat interval:

- 30 seconds

The heartbeat carries:

- runner state
- current DVD ID
- high-level stage
- process PID
- authorized Git HEAD
- batch number / processed count when available

If the runner dies without finalization, the Downloader status panel will
eventually show a stale runner state instead of falsely claiming normal
activity.

### Crash policy

The bulk runner does not silently recover durable RUNNING or GENERATED
states. If either exists at startup, preflight fails closed.

`RUNNING` crash recovery remains the explicit existing
`Stage12RolloutStateStore.recover_running()` procedure after exact runtime
verification. GENERATED/publication ambiguity remains subject to the existing
reconciliation rules.

### Validation before live authorization

Offline validation required before commit:

- Python compile
- bulk-runner smoke
- Stage12 batch smoke
- Stage12 rollout smoke
- `git diff --check`

The next checkpoint is a read-only bulk preflight on the committed clean
worktree. Actual 143-title execution remains separately authorization-gated.

## 2026-09-18 — Stage12 production first4 PASS

Formal production Stage12 bulk execution was started with the repository
runner `teddy_discovery_stage12_bulk_runner.py`.

First production batch:

- FC2-PPV-4555371
- FC2-PPV-4575470
- FC2-PPV-4592689
- FC2-PPV-4640215

Result:

- processed: 4
- published: 4
- FAILED_RETRYABLE: 0
- FAILED_TERMINAL: 0
- systemic failure: none

Durable rollout state after completion:

- PUBLISHED: 33
- PENDING: 139
- UNRESOLVED: 1
- RUNNING/GENERATED: 0

The production runner heartbeat operated correctly and the Downloader
Settings mini-panel showed the current DVD ID and active processing state.

Deferred mini-panel improvements for the future File Management tab:

1. match the Downloader dark theme
2. replace internal stage names such as `STAGE11` with plain Korean labels
   such as `자막 생성·번역 중`
3. expose real stateful part progress from the execution path and show
   `current part / total parts` plus optional percentage

Do not derive part progress heuristically. It must come from the actual
stateful/Hermes part execution state.

Next operation:

- launch the same formal production runner for all remaining ordinary
  PENDING titles
- no new canary implementation
- no title-specific production logic

## 2026-09-19 — Stage12 malformed external JA incident

The long-running Stage12 production bulk stopped during batch 9.

Durable state at the stop:

- PUBLISHED: 63
- PENDING: 104
- FAILED_RETRYABLE: 4
- RUNNING: 1
- UNRESOLVED: 1
- stuck RUNNING title: `HAWA-345`

The bulk process was no longer running and heartbeat finalized as ERROR.

Root cause was confirmed by an exact route-only replay using the already
persisted HAWA-345 baseline artifact:

- external Japanese subtitle SRT contained an invalid non-positive cue index
- subtitle parser raised `SubtitleParseError`
- immutable Hybrid construction wrapped this as
  `HybridEvidenceValidationError`
- the live external-JA adapter did not map that evidence-validation failure
  into its normal external-subtitle validation boundary
- Stage12 therefore treated it as an unexpected systemic Stage11 exception
  and stopped the entire bulk run

This is a generic malformed-external-subtitle boundary defect, not a
HAWA-345-specific rule.

Generic fix:

- `build_external_ja_adapter()` now catches
  `HybridEvidenceValidationError` while constructing immutable external
  Hybrid evidence
- it maps the error to `ExternalSubtitleValidationError`
- the existing Stage11 route selector then conservatively rejects the bad
  external subtitle and continues as `ASR_ONLY`

Validation after the fix:

- `git diff --check`: PASS
- Python compile: PASS
- Stage11 live-adapter smoke: PASS
- Stage11 controller smoke: 46 PASS
- Stage12 batch smoke: PASS
- Stage12 bulk-runner smoke: PASS
- production HAWA-345 route-only replay:
  - `ROUTE=ASR_ONLY`
  - `EXTERNAL_OUTCOME=VALIDATION_FAILURE`
  - `ALIGNMENT_OUTCOME=NOT_ATTEMPTED`

No title/DVD-specific production branch was added.

HAWA-345 has durable baseline ASR and targeted second evidence but no
first-pass staging, CLEAN subtitle, controller report, Stage12 GENERATED
state, publication, or Jellyfin update.

Explicit `RUNNING -> PENDING` crash recovery is required before resuming
ordinary bulk processing.

### 2026-09-19 crash recovery completed

After confirming the old bulk PID was dead, HAWA-345 was the only active
rollout title, no GENERATED state existed, no Stage11 CLEAN/report existed,
and the canonical NAS Korean subtitle destination was absent,
`Stage12RolloutStateStore.recover_running("HAWA-345")` was executed.

Post-recovery durable state:

- HAWA-345: PENDING
- PENDING: 105
- PUBLISHED: 63
- FAILED_RETRYABLE: 4
- UNRESOLVED: 1
- RUNNING/GENERATED: 0

The four FAILED_RETRYABLE titles remain excluded from ordinary PENDING bulk
selection and will be handled separately after the ordinary PENDING queue.

## 2026-09-23 — Stage12 bulk complete and failure forensic

The formal Stage12 bulk live run completed normally. This is the latest
authoritative production state and supersedes earlier pending-count and
next-operation notes in this handoff:

- `STAGE12_BULK_LIVE=COMPLETE`
- `PROCESSED_THIS_RUN=28`
- final rollout: `PUBLISHED=152`, `FAILED_RETRYABLE=20`, `UNRESOLVED=1`,
  `PENDING=0`
- final publications, including `VEC-737` and `VEMA-246`, completed normally

A read-only forensic pass compared the rollout DB events and provenance,
existing bulk logs, local artifacts/staging, and current repository code.
No rollout state, retry, recovery, live execution, NAS/Jellyfin write, or
source change was made during that pass.

### FAILED_RETRYABLE — ASR audio timeline validation (9)

Titles:

- `HMN-899`
- `NHDTC-250`
- `PRED-889`
- `SGKI-075`
- `SGKI-106`
- `SNOS-334`
- `SVFLA-014`
- `SW-216`
- `NIMA-059`

Exact recorded failures:

- Eight titles: `ASRAudioValidationError: audio frame timestamp has an unsafe
  discontinuity`
- `NIMA-059`: `ASRAudioValidationError: resampler output cannot reconcile to
  source end`

The point at which the iterator failed varied by title. Remote ASR call
history for the failed titles was:

- zero calls: `HMN-899`, `PRED-889`, `SGKI-075`, `SGKI-106`, `SNOS-334`,
  `SW-216`
- six earlier 600-second chunks had already been sent for `NHDTC-250`
- fifteen earlier chunks had already been sent for `SVFLA-014`
- ten full chunks had already been sent for `NIMA-059`; its final partial
  chunk was not yielded because the iterator rejected the EOF/source-end
  reconciliation

The iterator exception happens while preparing the next chunk, so prior
yielded chunks can already have crossed Remote ASR before a later timeline or
EOF error. Typed `ASRAudioError` failures remain isolated to individual
titles; they no longer stop the batch.

### Generic decoded-sample-clock correction

Implemented in `teddy_discovery_asr_audio.py`; this section supersedes the
earlier trigger-pair-only replay note below:

- The first decoded frame timestamp anchors the output timeline unchanged.
- Later frames are checked against the exact cumulative decoded-sample clock.
  Strictly duplicate/backward raw PTS fail closed.
- Bounded timestamp jitter/overlap is corrected by moving the canonical frame
  start to the decoded sample clock. Per-frame correction is limited to one
  preceding decoded-frame duration. The absolute **peak signed net offset** is
  limited to three adjacent decoded-frame durations (64 ms for 1024-sample AAC
  at 48 kHz).
- A forward deviation larger than the existing timestamp tolerance stays a
  segment boundary: flush the old resampler and preserve the exact interval as
  silence. It is not absorbed into timestamp correction.
- Raw PTS, sample-clock expected PTS, per-frame correction, current signed
  offset, peak absolute net offset, one-second window net/absolute correction,
  lifetime absolute correction, preserved gap count/duration, overlap count,
  EOF output counts, and fail-closed reason are structured diagnostics.
- EOF still requires resampled output to reconcile within one 16 kHz sample
  of the corrected source end. No decoded audio samples are dropped or
  duplicated, and the existing absolute chunk/sample boundaries remain in
  force.

Lifetime absolute correction remains a diagnostic only. It is not a production
reject criterion because long alternating ±1-tick timestamp jitter in the
already-PUBLISHED 44.1 kHz control `SIRO-4448` produced 2,253 tiny corrections
totalling 102.177 ms while its signed EOF drift was zero and peak net offset
was only 22.676 µs. The old lifetime-sum guard incorrectly rejected it. The
three-frame peak bound remains unchanged; it now rejects sustained same-way
timeline movement while allowing that zero-mean jitter.

### Full-media read-only replay — 2026-09-23

Replayed all nine failed titles, the three previously used PUBLISHED controls,
and ten additional PUBLISHED controls selected by source-size quantiles from
the rollout DB (bounded selection; no NAS-wide scan). Each source path, size,
and mtime matched the rollout row before replay. Production iterator/decode,
resample and chunking ran to EOF; failed titles also received an in-memory
diagnostic continuation to EOF after their exact production fail point. That
continuation does not change the production decision or validator bound. Each
source SHA-256 was recorded; the source copy used the dedicated
`/var/tmp/teddy-stage11-asr-replay` directory, and every title cleanup was
verified empty before checking `df -h /var/tmp` and `free -h` and starting the
next. `/tmp` was not used for media. Forward gaps are counted as gaps and
preserve silence. The following values are in seconds unless marked otherwise;
`window` is the maximum correction within the one-second diagnostic window.

| DVD-ID | Production | Full decoded frames | Overlap events / lifetime absolute | Max single correction | EOF signed / peak net | 1s window net / absolute | Forward gaps: count / duration / max | EOF expected → resampled (mismatch) | Production fail point |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| HMN-899 | FAIL | 400,294 | 60,222 / 20.218 s | 0.667 ms | +20.218 s / 20.218 s | 3.667 / 3.667 ms | 30,655 / 20.218 s / 0.667 ms | 136,957,179 → 136,957,178 (−1) | frame 1,690, PTS 1,730,560; peak net > 3 frames |
| NHDTC-250 | PASS | 515,004 | 2 / 20.229 ms | 19.542 ms | +20.229 / 20.229 ms | 19.542 / 19.542 ms | 2,747 / 157.944 s / 63.854 ms | 178,315,129 → 178,315,129 (0) | — |
| PRED-889 | FAIL | 344,708 | 53,649 / 17.942 s | 0.667 ms | +17.942 s / 17.942 s | 3.667 / 3.667 ms | 29,474 / 125.508 s / 64 ms | 119,668,464 → 119,668,464 (0) | frame 1,780, PTS 1,847,728; peak net > 3 frames |
| SGKI-075 | FAIL | 408,245 | 60,210 / 21.554 s | 0.667 ms | +21.554 s / 21.554 s | 3.667 / 3.667 ms | 36,643 / 21.554 s / 0.667 ms | 139,692,491 → 139,692,490 (−1) | frame 1,275, PTS 1,305,616; peak net > 3 frames |
| SGKI-106 | FAIL | 378,701 | 59,639 / 20.141 s | 0.667 ms | +20.141 s / 20.141 s | 3.333 / 3.333 ms | 33,670 / 138.342 s / 64 ms | 131,476,752 → 131,476,752 (0) | frame 1,294, PTS 1,341,904; peak net > 3 frames |
| SNOS-334 | FAIL | 448,855 | 18,783 / 12.322 s | 0.667 ms | +12.322 s / 12.322 s | 2.333 / 2.333 ms | 38,121 / 65.460 s / 33.333 ms | 154,256,541 → 154,256,541 (0) | frame 2,323, PTS 2,390,035; peak net > 3 frames |
| SVFLA-014 | FAIL | 726,376 | 5 / 92.958 ms | 21.313 ms | +92.958 / 92.958 ms | 92.958 / 92.958 ms | 3,874 / 220.370 s / 63.5 ms | 251,462,257 → 251,462,257 (0) | frame 423,389, PTS 439,850,641; peak net > 3 frames |
| SW-216 | FAIL | 363,276 | 6,523 / 63.779 s | 21.313 ms | +63.738 s / 63.738 s | 65.75 / 65.75 ms | 8,094 / 164.979 s / 91.313 ms | 126,637,870 → 126,637,869 (−1) | frame 438, PTS 457,093; signed peak 66.292 ms exceeds 64 ms |
| NIMA-059 | FAIL | 298,090 | 4,763 / 99.229 ms | 20.833 µs | +99.229 / 99.229 ms | 41.667 / 41.667 µs | 2 / 156 ms / 92 ms | 101,750,549 → 101,750,549 (0) | frame 192,407, PTS 197,029,183; peak net > 3 frames |

The eight Group A files and NIMA still exceed the generic three-frame peak
bound over their full timelines; their production errors remain
`ASRAudioValidationError` and title-scoped. `NHDTC-250` is the only one of the
nine that passes full production replay. In SW-216, units matter: the early
production crossing is 66.292 ms, while the EOF diagnostic net offset is
63.738 **seconds**, not milliseconds.

All 13 PUBLISHED controls passed full replay with EOF mismatch of 0 or −1
sample. Twelve had zero canonicalized overlap and zero net/peak drift. The
exception, `SIRO-4448`, had the 2,253 tiny alternating corrections described
above and still passed with zero signed EOF drift. The controls covered both
forward-gap and no-gap sources. The additional bounded cohort was
`FC2-PPV-4660439`, `FC2-PPV-4640215`, `SNOS-120`, `SIRO-5537`, `MNGS-076`,
`FCT-201`, `DOKI-037`, `FNS-237`, `DOKS-689`, and `NHDTA-663`; all decoded AAC
at 48 kHz. Existing controls add both 44.1 kHz (`SIRO-4448`) and 48 kHz
(`FC2-PPV-4575470`, `FC2-PPV-4551303`). Existing controls included both short
and long files, and forward gaps ranged from none to 2940 events / 172.481 s.
The ten added controls each had zero overlap corrections; they exercised
forward-gap preservation and EOF/resampler accounting.

Regression validation passed: long alternating ±1-tick jitter, sustained
same-direction drift fail, per-frame unsafe overlap fail, duplicate/backward
PTS fail, forward-gap silence preservation, EOF mismatch fail, chunk boundary
regressions, ASR audio/source/remote/transcriber smokes, Stage11 controller/
live-adapter/deployment smokes, Stage12 batch/bulk-runner/rollout smokes,
Python compile, and `git diff --check`. No retry, live ASR/Whisper call, rollout
state change, NAS/Jellyfin write, remux, or transcode occurred.

Canary candidate among these nine: `NHDTC-250` only. It passed complete
production replay with two bounded overlap corrections, 2,747 forward gaps
preserved as silence, and exact EOF sample reconciliation. This is a replay
result, not a canary execution or retry approval.

### FAILED_RETRYABLE — Jellyfin external Korean subtitle recognition (6)

Titles:

- `FC2-PPV-4758058`
- `FC2-PPV-4973050`
- `MKON-126`
- `NHDTB-93803`
- `SDDE-763`
- `START-636`

Exact final failure for all six:
`Stage12BatchTitleError: Jellyfin external Korean subtitle not recognized`.
Each transitioned `RUNNING -> GENERATED -> FAILED_RETRYABLE`; Stage11 passed,
the generated artifact was validated, and publication recorded an atomic,
verified destination with its SHA-256. Read-only SHA-256 checks confirmed the
local `clean-ko-v1.srt` and controller report files still match the hashes
stored in rollout state.

The repository already has a Jellyfin refresh fallback, including full
refresh, but these attempts still ended in recognition failure after that
fallback. The artifact/report pair remains available and hash-matched, so it
may be reused only after the existing provenance/source checks pass. Inspect
the exact Jellyfin item/path and external subtitle stream state before another
recognition attempt.

- current-code root-cause status: **NOT RESOLVED**
- next action: **FIX_FIRST** — read-only item/path/stream reconciliation;
  preserve the verified artifacts for eligible reuse

### FAILED_RETRYABLE — semantic output validation retry exhausted (5)

Titles and failed part indexes:

- `FNS-235` — part 7
- `GDTM-091` — part 12
- `HMN-896` — part 5
- `MAAN-1193` — part 9
- `SCOP-830` — part 3

Exact final exception for each:
`StatefulSemanticOutputValidationRetryExhausted: semantic output validation
retry exhausted`; all recorded `attempts=2`, `max_attempts=2`. These failed
during semantic validation, before clean artifact acceptance/publication.
The DB/bulk evidence records the exhausted retry and part index; it does not
preserve a more specific validator message per title.

- current-code root-cause status: **NOT RESOLVED**
- next action: **MANUAL_REVIEW** — inspect rejected part output and its
  validation reason before choosing any targeted input/data correction or
  retry

### UNRESOLVED — JUR-750

`JUR-750` was already `UNRESOLVED` during `INITIALIZE_FROM_INVENTORY`, with
`SUBTITLE_INVENTORY_INVALID`; it has no execution history. The associated
noncanonical sidecar is `JUR-750.R6B2-Clean.ko.srt`.

- current-code root-cause status: **NOT RESOLVED**
- next action: **MANUAL_REVIEW** — decide explicitly how to handle the
  noncanonical sidecar before inventory resolution
- do not automatically rename, delete, or overwrite the sidecar

### Next Stage12 operation

Start with read-only forensic reconciliation of the six Jellyfin recognition
failures: verify each exact Jellyfin item/path and external subtitle stream,
then establish whether the existing hash-verified artifact can be reused.
Do not run retry/recovery or write to NAS/Jellyfin until the forensic result
supports a separately authorized operation. Keep the nine ASR failures and
five semantic failures out of blind retry; handle them using the actions above.

## Stage12 delayed Jellyfin indexing and publication reconciliation

The follow-up read-only Jellyfin forensic confirmed five prior recognition
failures already have the exact published sidecar visible in Jellyfin:

- `FC2-PPV-4758058`
- `FC2-PPV-4973050`
- `MKON-126`
- `NHDTB-93803`
- `SDDE-763`

For those five, current NAS sidecar, recorded publication SHA/provenance,
Jellyfin exact item path, external stream path, Korean language, and `subrip`
codec agree. The evidence supports delayed Jellyfin indexing as the common
false-negative: the original bounded polling window ended before the stream
appeared. There is no evidence for a shared filename, path, or SRT defect.
`START-636` remains different: its exact external Korean stream was absent at
the read-only check and must stay `FAILED_RETRYABLE` unless a later exact GET
proves recognition. Do not add a title-specific workaround.

The generic recognizer retains the item-specific Default refresh followed by
FullRefresh, but accepts a separate bounded `full_refresh_max_attempts` window.
The bulk runner allows 42 full-refresh polls at its existing 5-second cadence
(up to 205 seconds for that phase), while keeping the default-refresh window
unchanged. A visible stream is accepted only for the exact media item and
sidecar path, Korean language, external status, and `subrip` codec. If the
stream never appears, the existing title failure path remains in force.

Added `teddy_discovery_stage12_reconcile.py` as a separate, explicit one-title
reconciliation path. It does not regenerate Stage11 output, republish, write
NAS, or refresh Jellyfin. Before the rollout state can be reconciled, it
revalidates current Discovery and NAS source identity/fingerprint, the full
Stage11 baseline/CLEAN/report provenance, immutable publication event proof,
destination bytes and SHA-256, and exact Jellyfin item/stream evidence using
GET requests only. The only state write is the existing audited
`FAILED_RETRYABLE -> PUBLISHED` reconciliation after every check passes. The
bulk runner exposes this path only as explicit `--mode reconcile --dvd-id`
and requires `TEDDY_STAGE12_PUBLICATION_RECONCILE_AUTHORIZED` to be set to the
review token. No production reconciliation was run in this change; the five
titles were pending separate approval at the time of this implementation
commit. `START-636` cannot pass the stream-presence gate while its exact
stream is absent.

Smoke coverage:

- delayed visibility after FullRefresh succeeds within the added bounded
  polling window;
- permanently absent, wrong-path, wrong-language, non-external, and wrong
  codec streams are rejected;
- reconciliation rejects NAS SHA, source identity, and publication
  provenance mismatch without changing state;
- exact valid existing publication evidence reconciles in an isolated
  temporary fixture without Jellyfin writes;
- Stage12 batch, bulk runner, rollout, and reconciliation smoke tests pass;
- changed modules compile and `git diff --check` passes.

At the time of this implementation update, the next operation was one
explicit reconciliation per eligible title after separate review. Subsequent
production results are recorded below. Do not include `START-636` unless its
exact stream becomes visible. If it remains absent, use a dedicated read-only
scanner diagnostic to compare the exact item's library path and refresh/scan
visibility; leave rollout state unchanged until evidence proves the expected
stream exists.

## Stage12 production reconciliation canary — 2026-09-23

Ran one explicitly authorized reconciliation for `FC2-PPV-4758058` using
code HEAD `d18dd5ecde8743c8c780ddd4eaf9a4a493aec7cc`. Before execution, HEAD
matched exactly, the worktree was clean, and the title was
`FAILED_RETRYABLE`, transition sequence 4, with reason
`STAGE12_TITLE_FAILURE`. The targeted reconcile coordinator returned PASS:
`RECONCILIATION_RESULT=PUBLISHED`, reason `PUBLICATION_RECONCILED`.

Fresh evidence matched at reconciliation time:

- Canonical Discovery source path was
  `FC2-PPV/FC2-PPV-4758058/FC2-PPV-4758058.mp4`; source size and nanosecond
  mtime matched rollout state and NAS read-only `lstat`.
- Existing Stage11 CLEAN/report/baseline bundle passed provenance validation;
  CLEAN SHA-256 was
  `359c7293b4b1a8c6c11a640ee4834020fe6f0b7cbe48dd7aada4c1739b5aacf5`, and
  report SHA-256 matched recorded state.
- NAS destination
  `FC2-PPV/FC2-PPV-4758058/FC2-PPV-4758058.ko.srt` was read-only verified at
  1,908 bytes. Its SHA-256 matched both the Stage11 artifact and immutable
  publication proof.
- Jellyfin GET resolved item `f572f98325049203905b21a25a427aba` at the exact
  expected media path and reported the exact sidecar as an external `kor`,
  `subrip` subtitle stream.
- The reconciliation event records `controller_call_performed=false` and
  `nas_write_performed=false`; the code path used Jellyfin GET only and made
  no refresh/write request. No Stage11 rerun, translation, or republication
  occurred.

Afterward, only this title had a new rollout event: sequence 5,
`FAILED_RETRYABLE -> PUBLISHED`, reason `PUBLICATION_RECONCILED`. Final
rollout counts are `PUBLISHED=153`, `FAILED_RETRYABLE=19`,
`UNRESOLVED=1`, `PENDING=0`. `START-636` was not touched.

## Stage12 remaining Jellyfin reconciliation titles — 2026-09-23

After the canary passed, independently revalidated and reconciled the other
four forensic-approved titles. Each title was gated on its current
`FAILED_RETRYABLE` state, canonical Discovery source identity and NAS source
fingerprint, Stage11 baseline/CLEAN/report provenance, immutable publication
proof, NAS destination bytes/SHA, and a fresh Jellyfin GET for the exact item
and exact external KO stream (`Language=kor`, `IsExternal=true`,
`Codec=subrip`, exact expected sidecar path). All four passed. Each moved from
sequence 4 `FAILED_RETRYABLE` / `STAGE12_TITLE_FAILURE` to sequence 5
`PUBLISHED` / `PUBLICATION_RECONCILED`.

| DVD-ID | NAS sidecar bytes / SHA-256 | Jellyfin item ID |
| --- | ---: | --- |
| `FC2-PPV-4973050` | 795 / `0eab564e9a01ee5e70e61a4e05076b41861d4d7ab0a4d014b55fa16b6eb2a380` | `38558e5c4604af22e39557fe8b699d40` |
| `MKON-126` | 18,607 / `288b16e92029a6f22e974d9e4c625703afaa8e593a17b76887b7c5381269bace` | `db6af239d58cab308da599eaba297cba` |
| `NHDTB-93803` | 68 / `28676cd94f390ef965a8557512332c7a3d9ece65a9d6838f3c9c3ecdaa5e328f` | `d83183871bf60382367b987172d60c77` |
| `SDDE-763` | 42,342 / `bfe384e976f0311144804f099ed06f106820fcbe019ba792cfddc5dda057d8e9` | `9c9b380e38b05f9ae20fa5acd9ae808f` |

For every title, the local CLEAN SHA matched the report/provenance and the
read-only NAS destination SHA; the Jellyfin item and stream paths matched the
expected media and `.ko.srt` paths. Reconciliation used no controller call,
NAS write, or Jellyfin refresh/write. No Stage11 rerun, translation, or
republication occurred. The four appended rollout events are event IDs
724–727 and apply only to these four DVD-IDs. `START-636` remains
`FAILED_RETRYABLE` and was not touched.

Final rollout counts after the four-title sequence are `PUBLISHED=157`,
`FAILED_RETRYABLE=15`, `UNRESOLVED=1`, `PENDING=0`. Together with the earlier
canary, the complete five-title delayed-indexing group is reconciled; all
other rollout titles remain unchanged.

## START-636 delayed Jellyfin indexing diagnostic and reconciliation — 2026-09-23

The exact `START-636` Jellyfin item received one item-specific Default refresh
as a separate bounded diagnostic. The expected external Korean stream first
appeared on the second post-refresh PlaybackInfo poll, about 5.2 seconds after
the refresh. Its metadata was `Language=kor`, `IsExternal=true`,
`Codec=subrip`, and exact path
`/media/adult/START/START-636/START-636.ko.srt`; the item was
`157b376a8917d59c87de7b6ee5c01ec7` at
`/media/adult/START/START-636/START-636.mp4`. The stream appeared during the
Default polling window, so no FullRefresh was issued. This confirms delayed
Jellyfin indexing for the remaining title; no filename or sidecar workaround
was needed.

Then, using code HEAD `3155d1a455baa3753d5bf65271c6fb7089b874eb`, ran the
existing explicit one-title `--mode reconcile --dvd-id START-636` path. Before
execution, HEAD matched, the worktree was clean, and current read-only checks
confirmed `FAILED_RETRYABLE`, sequence 4, reason `STAGE12_TITLE_FAILURE`.
Discovery and NAS source identity matched at
`START/START-636/START-636.mp4` (1,801,037,186 bytes; mtime
1788861288542183653 ns). The existing Stage11 artifact/report bundle passed
provenance validation: CLEAN SHA-256
`e2400ea07c0a7f2b90885d6de2bf6231fffdafef20c61ceba236770b9cf2f629`, report
SHA-256 `fbe6e0390812bae89c51c98c19d7bf14777c41dedecf203101f7a9da8c9a0e6c`.
NAS sidecar `START/START-636/START-636.ko.srt` was 364 bytes; its read-only
SHA-256 matched both the CLEAN artifact and verified publication proof.
Jellyfin GET reconfirmed the exact item and stream metadata above.

Reconciliation passed: only `START-636` changed from sequence 4
`FAILED_RETRYABLE` / `STAGE12_TITLE_FAILURE` to sequence 5 `PUBLISHED` /
`PUBLICATION_RECONCILED` (event 728). The audited event records
`controller_call_performed=false` and `nas_write_performed=false`; reconciliation
used Jellyfin GET only and issued no refresh. No Stage11 rerun, translation,
republication, NAS write, or direct Jellyfin DB write occurred. A full
before/after snapshot of every other rollout title's status, sequence, and
reason was identical.

Final rollout counts are `PUBLISHED=158`, `FAILED_RETRYABLE=14`,
`UNRESOLVED=1`, `PENDING=0`. The separate diagnostic's one exact-item Default
refresh is recorded above; it did not alter rollout state or write the NAS
sidecar.

## Stage12 explicit FAILED_RETRYABLE retry path — 2026-09-23

Added `teddy_discovery_stage12_bulk_runner.py --mode retry` as a generic,
operator-authorized single-title path from `FAILED_RETRYABLE` through the
existing Stage11 controller, Stage12 artifact validation/publication, and
Jellyfin external-stream check. This path is separate from ordinary bulk
`live` selection and publication-only `reconcile`.

The retry command requires exactly one `--dvd-id`, a positive
`--expected-sequence`, exact `--expected-head`, a clean worktree, and the
separate `TEDDY_STAGE12_EXPLICIT_RETRY_AUTHORIZED=YES_I_HAVE_REVIEWED_THE_SINGLE_TITLE`
authorization. It fails closed on active RUNNING/GENERATED rollout state,
state/sequence mismatch, Discovery or NAS source fingerprint drift, existing
destination, inconsistent event history, or recorded artifact/publication
provenance. The durable transition is directly
`FAILED_RETRYABLE -> RUNNING`, reason `STAGE12_EXPLICIT_RETRY_START`, with the
authorized sequence recorded in event provenance; the database update is
sequence-guarded. Retry execution uses the normal `Stage12BatchRunner._run_one`
path with immutable one-title selection. Any title failure follows the
existing Stage12 failure classification; retryable failures return to
`FAILED_RETRYABLE`, while existing terminal safety conflicts retain their
terminal handling.

No production retry was run while implementing this path. Read-only rollout
state still showed `NHDTC-250=FAILED_RETRYABLE`, sequence 3,
`STAGE12_TITLE_FAILURE`, source size 6,618,791,523 bytes, and source mtime
1788879891350125554 ns. Rollout counts were `PUBLISHED=158`,
`FAILED_RETRYABLE=14`, `UNRESOLVED=1`.

Offline retry smoke passed: exact one-title selection, missing/duplicate
selector rejection, absent authorization, status/sequence/fingerprint and
artifact-provenance guards, title failure isolation, normal Stage11 and
publication path reuse, and unchanged other-title state. Existing Stage12
batch, bulk-runner, rollout, and reconciliation smokes also passed; compile
and `git diff --check` passed. The retry command shape for the later NHDTC-250
canary is:

```sh
TEDDY_STAGE12_EXPLICIT_RETRY_AUTHORIZED=YES_I_HAVE_REVIEWED_THE_SINGLE_TITLE \
  /opt/stage11-stt-venv/bin/python /opt/missav-pwa-subtitle-stage11/teddy_discovery_stage12_bulk_runner.py \
  --mode retry --batch-size 1 --max-titles 1 \
  --dvd-id NHDTC-250 --expected-sequence 3 \
  --expected-head <exact-clean-authorized-HEAD>
```

Replace the HEAD value only after checking the exact clean code revision at
execution time. This command has not been run.

## Production ASR media temp storage — 2026-09-23

The CT108 tmpfs incident was traced to the production Stage11 factory creating
`ASRMediaSourceReader` without `temp_root`; `tempfile.mkdtemp(dir=None)` then
resolved to `/tmp`. A 6,618,791,523-byte source could be fully copied there,
contributing to RAM/swap exhaustion and an SSH outage. No production retry or
media copy was run for this fix.

The shared Stage11 deployment config now injects
`/var/tmp/teddy-stage11-asr-production` with disk-backed filesystem validation
for both ordinary Stage12 bulk and explicit retry. The reader rejects `/tmp`,
symlinked/non-private/unwritable roots, and non-disk filesystem types without
fallback. After remote source stat, preflight requires
`source_size_bytes + 4 GiB` free. A single-source bound is sufficient because
the Stage12 runner lock excludes competing bulk/retry runs, batch execution is
serial, and the baseline transcriber cleans its source in `finally` before the
controller can invoke the targeted adapter; targeted evidence uses its own
context-managed copy afterward.

Partial transfer catches `BaseException`, aborts the transfer child, removes
only that request's media file/directory, and re-raises the primary failure.
Normal baseline/targeted use cleans the same per-request directory. Cleanup
outcome, temp-root resolution, source size, free bytes, required bytes, and
request-directory basename are logged. Existing source identity and mtime
checks are unchanged.

Tiny-payload temp policy smoke passed root creation/permissions, free-space
pass/fail, sibling-directory preservation, sequential baseline/targeted
lifecycle, and partial-copy cleanup for `Exception`, `KeyboardInterrupt`, and
`SystemExit`. ASR source/audio/transcriber, Stage11 adapter/controller/
deployment, Stage12 retry/batch/bulk/rollout/reconciliation smokes, compile,
and `git diff --check` all passed. No large media fixture, Remote ASR, Whisper,
rollout mutation, or NAS/Jellyfin write was used.

## Stage13-B read-only Library backend — 2026-09-28

Implemented a GET-only `/api/library` read model and runtime installation for
the Stage13 File Manager. The list is sourced from current `jav` holdings with
`present=1`; Stage12 rollout rows are read-only optional state. Detail and
playback resolve a canonical DVD-ID through the current holding before using
its canonical media identity. No delete route or new player was added.

`GET /api/library` supports case-insensitive DVD-ID/title search, KO
`present`/`absent`, unresolved and mismatch filters, and the requested six
sort keys. `GET /api/library/<dvd_id>` validates the canonical ID.
`GET /api/library/<dvd_id>/stream` reuses `teddy_storage`'s existing SSH
Range response implementation with the fixed JAV root; clients cannot submit
a path. API errors use the existing JSON `status/error.code/message` shape.

Managed size reads only DB-derived canonical title folders over the existing
dedicated NAS SSH identity and known-host boundary. One bounded inventory
request covers the holdings in a list call (maximum 250 holdings, 512 entries
per title, depth 5, 30,000 entries overall, 16 MiB canonical subtitle payload,
64 MiB response). Symlinks, unexpected entry types, limits and transport
failures produce an unknown total with a reason code. The summary reports the
sum of known item bytes plus completeness and unknown count.

KO status reuses Stage12's `_classify_subtitles`, canonical sidecar candidate
selection and SRT parser using bounded NAS inventory/read data. Stage12
terminal state and reason are an optional left join; Stage12 `UNRESOLVED`
stays distinct from ordinary absence. Jellyfin uses one GET-only path inventory
request bounded to 10,000 items; exact path matches are recognized, complete
inventory misses are absent, and incomplete/failed requests are unknown.

NAS added date never uses media filesystem timestamps. A matching
`COMPLETED` organizer job must target the exact canonical media relative path;
its creation and completion timestamps must resolve to the same KST date.
That date is labeled `ORGANIZER_COMPLETION_BOUNDED_DATE` with
`nas_added_at=null`; otherwise the value remains unknown. This is a bounded
date claim, not an exact placement instant.

The app container receives the rollout DB, NAS dedicated key/known_hosts and
Jellyfin API key through read-only mounts. It does not mount the JAV library
locally. A read-only API source smoke against the production Discovery and
rollout databases returned 177 current holdings independently of the 173
rollout rows and retained EBWH-296, MIAD-866, MIRD-258 and SKMJ-774. The
production database files were mounted read-only for this smoke. No production
database/NAS/Jellyfin write, NAS/Jellyfin request, refresh, Hermes or VM122 call
occurred.

The fixture smoke covers holdings absent from rollout, normalized subtitle
states, KST same-date/cross-date behavior, no mtime fallback, bounded size and
failure states, searches, filters, every sort mode, invalid requests,
canonical playback identity/path traversal rejection, Jellyfin recognized /
absent / unknown behavior, runtime route installation, auth guard, and
byte-for-byte unchanged fixture databases. The full Docker image build and the
Stage12 inventory, Jellyfin, Downloader API and existing stream-range smokes
passed. `python -m py_compile` and `git diff --check` passed. Next checkpoint:
Stage13-C File Manager UI.

## Stage13-C File Manager UI — 2026-09-28

Added a separate `영상 라이브러리` SPA tab backed by the GET-only Stage13-B
`/api/library` list response. The existing Files page remains intact. The new
page renders the current holdings summary, server-side DVD-ID/title search,
KO/unresolved/mismatch filters and Library API sort modes. Expandable rows
reuse Discovery row/detail styles and show cover, identity, metadata, managed
relative path, subtitle/Stage12/Jellyfin states, NAS date provenance and
bounded size status. Unknown date/size and incomplete library totals remain
explicitly unknown; no browser-side timestamp or size fallback is used.

Playback uses the existing video modal and `<video>` element through the
canonical DVD-ID `/api/library/<dvd_id>/stream` adapter. Existing Files
preview continues through the same shared modal. Covers use the existing
Discovery cover route. No delete control or request was added. The UI has no
per-item detail fetch and makes no per-item playback/Jellyfin requests.

Validation passed: new File Manager UI shell smoke, existing Discovery UI
shell smoke, subtitle status UI smoke, Stage13-B fixture Library API smoke in
the Docker image, Python compile, `git diff --check`, and a full Docker image
build. Responsive CSS breakpoints were checked by the UI shell smoke; no
browser rendering harness is installed in the local environment. This is a
source-only checkpoint: no production deployment/restart, database/NAS write,
Jellyfin write/refresh, or delete request was performed. Next checkpoint:
Stage13-C production deployment preflight and read-only canary.

## Stage13-C production deployment attempt and rollback — 2026-09-28

Preflight began from clean source HEAD
`853930c05b92ec03363199eafbada1099cf033da` on
`teddy-subtitle-stage11`; the exact GitHub branch matched. Production Compose
was `/opt/missav-dlp-web/compose.yaml` with its existing
`/opt/missav-dlp-web/gluetun.env`. Candidate rendering kept all four service
definitions, unrelated services, Downloader port 58000, network, restart
policy and existing storage mounts unchanged. The app retained its
read-only dedicated NAS key/known_hosts and rollout DB mounts, gained the
existing Jellyfin API key as a read-only file mount, and received the
`TEDDY_NAS_*`, `TEDDY_JELLYFIN_*` and `TEDDY_STAGE12_ROLLOUT_DB` environment
names required by Stage13 runtime. No local JAV mount was added. Only the
Downloader web service was recreated; Gluetun and browser services were not
restarted.

The exact source built successfully as image
`sha256:5b7aa9cdbe3344f541ff321ea30925aede10beda69127385409c04a510d75247`,
tagged `ghcr.io/ssikgun/missav-dlp-web:stage13c-853930c05b92` and labeled with
the source revision. Library API and static UI assets were present. External
unauthenticated checks retained `/` redirect and API 401 behavior; Library
JS/CSS returned 200.

The production read-only canary reported 177 present holdings independently
of the 173 Stage12 rows, including EBWH-296, MIAD-866, MIRD-258 and SKMJ-774.
Counts were KO `VALID=163`, `UNRESOLVED=10`, `ABSENT=4`, mismatch 0. Known
managed size summed to 509,297,211,868 bytes with `size_complete=true` and
zero unknown items. Two historical bounded dates had
`nas_added_at=null` and `ORGANIZER_COMPLETION_BOUNDED_DATE`; the unknown-date
sample remained null/`UNKNOWN`. Two positive managed-folder sizes were
confirmed. Jellyfin returned 177 exact recognized paths. DVD-ID/title search,
KO present/absent and unresolved filters, plus NAS date/DVD-ID/size sorts
passed. A canonical playback adapter request returned HTTP 206 for bytes
0–2047 (2,048 bytes); no full media was read or saved. These requests used
bounded exact DB-derived title paths and one bounded Jellyfin GET inventory.

Canary failure: Stage12 rollout rows for HMN-899 and NHDTC-250 contained
distinct terminal reasons `STAGE12_UNSAFE_AUDIO_TIMELINE` and
`STAGE12_BASELINE_ASR_NO_SPEECH`, but the Library API selected the generic
`inventory_reason=NO_CANONICAL_KO_SRT` first and returned
`STAGE12_UNRESOLVED` / `자막 상태 확인 필요` for both. JUR-750 correctly
returned `SUBTITLE_INVENTORY_INVALID` / `기존 자막 상태 확인 필요`. The
distinct Stage12 reason mapping therefore did not meet the production canary
contract. This source defect must be fixed and fixture-tested before another
deployment attempt. No subtitle body or raw artifact was emitted.

The web app alone was rolled back to the captured prior image
`sha256:fb1e9c6dc655c3cd7044e8a8c1711414589e2c1695503e866fe178c3396e6b79`.
It is running with the original compose configuration; the NAS key remains
read-only and no Jellyfin key mount or Stage13 aliases remain. Other services
remained running. A browser binary exists in the separate browser container,
but no authenticated rendering session/harness was available; visual viewport
verification remains pending manual review. The deployed Stage13 image did
not pass canary and is not the active production image.

Production write audit for this attempt: Discovery/rollout DB writes 0, NAS
writes/deletes 0, Jellyfin writes/refreshes 0, Hermes calls 0, VM122 calls 0,
subtitle generation 0, permanent deletes 0. Only the Downloader app container
was deployed and rolled back. Next: correct terminal-reason precedence or
normalization, run the fixture smoke and exact-source deployment preflight
again, then repeat the read-only canary.

## Stage13-C1 unresolved reason resolver hotfix — 2026-09-28

Updated the Library `_reason()` resolver to inspect
`last_transition_reason` and `inventory_reason` independently, using the
existing `UNRESOLVED_LABELS` concrete reason list. A specific transition
reason now wins when present; otherwise a specific inventory reason remains
authoritative. Only when neither field contains a known concrete reason does
an unresolved terminal state use `STAGE12_UNRESOLVED` / `자막 상태 확인 필요`.
The inventory-only helper call path remains supported. No per-title behavior
or DVD-ID mapping was added.

Fixture cases passed for unsafe audio timeline, baseline ASR no speech,
inventory-invalid-only, generic unresolved, and inventory-only helper
compatibility. The complete Stage13-B fixture Library API smoke, Stage13-C
Library UI shell smoke, Stage12 holdings inventory smoke, Python compile and
`git diff --check` passed. These tests used fixtures only. Production was not
deployed or restarted; DB/NAS/Jellyfin writes, Hermes/VM122 calls, subtitle
generation, and delete operations were all zero. Production remains on the
previous known image after the Stage13-C1 source fix. Next: build and deploy
the corrected source candidate, then rerun the Stage13-C production
read-only canary.

## Stage13-C2 hotfix production redeploy and canary — 2026-09-28

Built exact source HEAD `044be13a507b20bb1040eb432cb16cb8deb22233` as
`ghcr.io/ssikgun/missav-dlp-web:stage13c2-044be13a507b` with image ID
`sha256:2ac1125af07b5f55e78daa85030a9e32c793e44eb1182a3cff0fe58e34a48566`.
The source revision label and Library API/UI assets were verified. Using the
production Compose file and env source, only `missav-dlp-web` was recreated;
the original port, network, storage mounts and read-only NAS/rollout/Jellyfin
secret boundaries were retained. Gluetun and browser service container IDs
were unchanged. The new image is running with restart count 0. No rollback was
performed.

The production read-only Library list canary passed with 177 current
holdings, `VALID=163`, `UNRESOLVED=10`, `ABSENT=4`, and mismatch 0. It retained
EBWH-296, MIAD-866, MIRD-258 and SKMJ-774. Exact reason results were:
HMN-899 `STAGE12_UNSAFE_AUDIO_TIMELINE` / `오디오 타임라인 이상`, NHDTC-250
`STAGE12_BASELINE_ASR_NO_SPEECH` / `음성 대사 없음`, and JUR-750
`SUBTITLE_INVENTORY_INVALID` / `기존 자막 상태 확인 필요`. None returned the
generic fallback. This closes the Stage13-C1 production reason blocker.

Bounded representative NAS/Jellyfin check for ADN-785 returned positive known
managed size, NAS date `2026-09-01` with `nas_added_at=null` and
`ORGANIZER_COMPLETION_BOUNDED_DATE`, and Jellyfin `RECOGNIZED`. HMN-899 Library
playback returned HTTP 206 for bytes 0–1023 (1,024 bytes); no media body was
saved. The existing Files list helper returned zero remote media entries, so
there was no safe existing Files item on which to run the requested Range
regression. No arbitrary path was tried. The Files playback Range canary
remains unverified until an existing remote Files entry is available.

Library JS/CSS returned HTTP 200. The deployed template has Library, Discovery
and Files tabs, one shared video element/modal, and the Library DVD-ID stream
adapter; no Library delete UI/request exists. Public auth behavior remained
`/` redirect and API 401. A Chrome process exists in the separate browser
container, but there is no authenticated DevTools/render harness; visual
viewport verification is `PENDING_MANUAL`.

No rollback. Production write audit: DB writes 0, NAS writes/deletes 0,
Jellyfin refresh/write 0, Hermes 0, VM122 0, subtitle generation 0, permanent
delete 0. Production remains on image
`sha256:2ac1125af07b5f55e78daa85030a9e32c793e44eb1182a3cff0fe58e34a48566`.
Next: verify existing Files playback when a remote Files media item is
available, then perform authenticated desktop and narrow/mobile viewport
review. The deployed candidate is retained while those checks are pending.

## Stage13-C3 File Management navigation refactor — 2026-09-28

Refactored the frontend navigation without changing Library, subtitle-status,
or Files API contracts. The sidebar now has one folder-icon `파일 관리`
entry, opening the former Library SPA page renamed for users. Its default
subtab is `보유 라이브러리`; `자막 처리 현황` is a sibling subtab. The status
panel was removed from Settings and placed under File Management with a note
that pipeline job counts are separate from holdings. Status labels now use
text-oriented emoji labels instead of traffic-light symbols. `/api/subtitles/status`
loads on status-subtab activation and polls every 10 seconds only while both
the File Management page and status subtab are active.

The existing standalone Files content was moved under Download as the
`정리 전 파일` tab beside default `다운로드 작업`. Existing file control IDs,
`fetchFiles`, search/sort, actions, and `/api/files/.../stream` playback are
retained; opening the subtab invokes `fetchFiles`. The explanatory text notes
that files disappear from this view after organizer movement to the JAV
library. The shared video player remains singular and no permanent Library
delete UI/request was added. Discovery and Settings controls remain present.

Updated the Library, subtitle-status, Discovery shell checks and added
`teddy_file_management_navigation_smoke.py`. Those checks, subtitle status
fixture smoke, Python compile, and `git diff --check` passed. The complete
local Docker image build passed as
`missav-stage13c3-smoke:c87500b` (`sha256:0b2622d358401fc107dab6324ce1d933f145a22933a76e758665525c6a56eaa6`).
Its existing Browser build patcher was updated to anchor on the renamed single
File Management route and current Discovery page position.

This checkpoint did not deploy or restart production. Production app image
remains `sha256:2ac1125af07b5f55e78daa85030a9e32c793e44eb1182a3cff0fe58e34a48566`.
DB/NAS/Jellyfin writes, Jellyfin refreshes, subtitle generation, permanent
delete, Hermes calls and VM122 calls were all zero. Next: deploy the new UI
source separately, then perform authenticated manual desktop and narrow/mobile
visual acceptance.

## Stage13-C4 File Management production redeploy and focused canary — 2026-09-28

Built exact source revision
`6063c51247f1f2dc919fe583557482b225bbdd8c` as
`ghcr.io/ssikgun/missav-dlp-web:stage13c4-6063c51`; image ID is
`sha256:46b71ff6fdbc2a4d764b2fc6d62877c2e82750176b4c98f4e60641eb2d255d38`.
The image revision label matches the full source SHA and Library/navigation
assets were present. Candidate Compose rendering used the production
`compose.yaml`, `gluetun.env`, existing C2 override and an app-image-only
override. App port/network/storage and read-only secret, Discovery DB,
Stage12 DB/runtime and Jellyfin mounts matched the running configuration.
Only `missav-dlp-web` was recreated with `--no-deps`; gluetun and both browser
container IDs did not change. The app is running with restart count 0; no
container healthcheck is configured, and `/login` returned HTTP 200.

Deployed image static/runtime checks confirmed exactly one File Management
sidebar entry, no standalone Files or Video Library entry, and retained
Download, Discovery, Browser and Settings entries. File Management has the
`보유 라이브러리` default tab and `자막 처리 현황`; Download has
`다운로드 작업` default and `정리 전 파일`. Settings retains its config
controls and no subtitle status panel. The status API path, active-page plus
active-subtab polling guard, 10-second interval, semantic status labels,
single shared video element, separate Library and Files stream wiring, and
absence of Library delete UI/request were confirmed from the deployed image.

The production read-only Library model returned 177 current holdings,
`VALID=163`, `UNRESOLVED=10`, `ABSENT=4`, mismatch 0; all four holdings without
Stage12 rows remained present. Known managed size totaled 509,297,211,868
bytes with complete=true and zero unknown items. HMN-899, NHDTC-250 and
JUR-750 retained their concrete expected reason codes and Korean labels.
Bounded representative NAS sizes were positive, ADN-785 had date
`2026-09-01` with `nas_added_at=null` and
`ORGANIZER_COMPLETION_BOUNDED_DATE`, and representative Jellyfin GET matches
were `RECOGNIZED`. The subtitle status read-only snapshot was `idle`, with
163 PUBLISHED, 10 UNRESOLVED, no active DVD-ID, and the existing heartbeat
marked stale; last activity was retained by the status source.

The canonical ADN-785 stream mapping passed to the existing Range helper and
returned 206 for bytes 0–1023 (1,024 bytes); the body was not saved. This was
an internal helper canary, not an authenticated HTTP route request. The
existing Files metadata helper reported zero current entries, so
`TRANSIENT_FILES_RANGE_CANARY=N/A_NO_CURRENT_FILE`. The old Files API,
`fetchFiles`, search/sort, action and stream wiring remain in the deployed
image. Unauthenticated `/` retained its login redirect, `/api/library`
returned 401, and Library JS/CSS plus subtitle JS returned HTTP 200. No
authenticated HTTP or DevTools browser harness was available, so the
authenticated API route/interactive subtab lifecycle and desktop/mobile
visual viewport remain pending Teddy review; no auth bypass was used.

The new image remains deployed; no rollback was performed. Production write
audit: DB writes 0, NAS writes/deletes 0, Jellyfin refresh/write 0, Hermes 0,
VM122 0, subtitle generation 0, permanent Library delete 0. Only the web app
image/container was replaced. Next: Teddy performs authenticated desktop and
narrow/mobile review, including the subtab interactions and playback button.

## Stage13-C5 subtitle status dark-theme CSS hotfix — 2026-09-28

Added scoped `html[data-theme="dark"]` overrides to
`templates/teddy-subtitle-status.css`. The panel now uses the existing
`#111827` dark surface and `#273449` border; metric cards and badges use the
existing `#1f2937` secondary surface with readable foregrounds. Title,
current status, metric values/labels and footer use the established dark
theme text palette. Every badge state, including idle, running, attention,
stale, error and unavailable, remains legible with neutral styling; emoji and
text continue to carry the state meaning. Existing light-theme base values
and the 680px two-column metric layout were left unchanged.

Extended `teddy_subtitle_status_ui_smoke.py` to check dark selectors and
foreground/background declarations, preserve the light base declarations,
and retain the narrow grid. Subtitle status UI, File Management navigation,
Library UI, Discovery UI shell, Python compile and `git diff --check` passed.
The full local Docker image build `missav-stage13c5-smoke:9692b06` passed,
including all configured UI smoke checks.

No production deploy or restart was performed. Production remains on the C4
candidate image `sha256:46b71ff6fdbc2a4d764b2fc6d62877c2e82750176b4c98f4e60641eb2d255d38`.
DB/NAS/Jellyfin writes, Jellyfin refresh, Hermes/VM122 calls, subtitle
generation and delete operations were all zero. Next: deploy the CSS hotfix
by replacing only the production web app, then Teddy verifies dark-mode status
panel appearance.

## Stage13-C6 subtitle status dark-mode production redeploy — 2026-09-28

Built exact source HEAD `b63bd132bc75753b8b1127cb792e42c4b33e8324` as
`ghcr.io/ssikgun/missav-dlp-web:stage13c6-b63bd13`. The production image ID
is `sha256:7f427ebf957180466c7fe0d56122dd5eddfc833f3919ab9527741d8a1399df19`;
the OCI revision label matches the source HEAD. Before replacement, the
running C4 rollback image was recorded as
`sha256:46b71ff6fdbc2a4d764b2fc6d62877c2e82750176b4c98f4e60641eb2d255d38`.
The production Compose/env and existing overrides were rendered with only
the app image changed. Only `missav-dlp-web` was recreated using
`--no-deps`; gluetun and both browser services kept their prior container
IDs. The new app is running with restart count 0, and `/login` returns 200.

The live-served `teddy-subtitle-status.css` returned 200 and passed checks for
the dark panel selector/surface/border, current text, metric surface/value/
label, footer and badge override. Existing light panel/metric base values and
the 680px two-column layout also passed. Status JS returned 200 and retained
all six semantic status labels. No runtime/status enum, API, or navigation
source changed.

Read-only production holdings source returned 177 rows. The existing status
snapshot builder returned normally (`idle`, 163 PUBLISHED, 10 UNRESOLVED,
heartbeat present); unauthenticated `/api/subtitles/status` and
`/api/library` requests returned the expected 401. No authenticated browser
or DevTools harness was available, so API contents were checked through the
same read-only source builders rather than bypassing auth. Deployed template
checks confirmed File Management/Download navigation, Settings controls,
Discovery, Library playback wiring, a single shared video element, and no
Library delete UI/request. Static Library, Discovery and status assets
returned 200. `VISUAL_DARK_THEME_CANARY=PENDING_TEDDY`.

No rollback. Production write audit: DB writes 0, NAS writes/deletes 0,
Jellyfin refresh/write 0, Hermes 0, VM122 0, subtitle generation 0, Library
delete 0. The current production image remains
`sha256:7f427ebf957180466c7fe0d56122dd5eddfc833f3919ab9527741d8a1399df19`.
Next: Teddy opens `파일 관리 > 자막 처리 현황` with dark theme enabled and
confirms the panel appearance in the real browser.

## Stage13-E1 Permanent Delete DRY-RUN prepare/validate — 2026-09-28

Implemented read-only `POST /api/library/<dvd_id>/delete/prepare` and
`POST /api/library/<dvd_id>/delete/validate`. Both require the existing
authenticated session, JSON request, exact same-origin `Origin`, and the
explicit `X-Teddy-Delete-Intent` header. The request identity accepts only the
canonical DVD-ID; the server re-reads the current present JAV holding and
revalidates its canonical mapping. No arbitrary path or filename is accepted.

Prepare and validate use the existing hardened dedicated `CompletionSSH`
transport and inspect one database-derived title directory only. The
read-only `lstat` manifest rejects unsafe components, root escape, symlinks,
special files, nested directories and entry overflow. Its SHA-256 covers
canonical sorted manifest metadata (relative filename, size, mtime_ns, inode,
device and regular-file type), not media contents. The holding's canonical
media size and mtime_ns must match. Stage12 subtitle state and Jellyfin state
are read-only summary fields; no subtitle content is returned.

Prepare tokens are cryptographically random, process-memory only, DVD-ID / manifest /
holding-identity bound, five-minute TTL and bounded to 128 entries. Validation
re-reads the holding and exact manifest. Drift fails closed as
`MANIFEST_CHANGED`; identical successful replay returns the same validation
result. The Library detail UI requires both the explicit acknowledgement and
an exact typed DVD-ID, displays the safe manifest summary, and stores the token
only in memory. Closing the dialog clears it. Successful validation displays
`삭제 준비 검증 완료 · 실제 삭제는 아직 비활성`; no commit endpoint exists.

Added a non-persistent safe future provenance dataclass/serializer contract
(`schema_version`, DVD-ID, manifest SHA, counts/bytes, phase, source identity
fingerprint, timestamps and result). Fixture smoke covers valid and invalid
identity, duplicate/missing holdings, path traversal, root/family/title and
child symlinks, special files, nested directory, entry bound, missing/drifted
canonical media, stable order/hash, token binding/expiry/replay, missing
acknowledgement, subtitle/Jellyfin read-only states, query-only DB bytes, and
the absence of a deletion primitive. Existing Library API, Library UI,
File Management navigation, subtitle status, and Discovery smokes passed.
Python compile and `git diff --check` passed; full Docker build
`missav-stage13e1-smoke:874d3aa` passed.

Stage13-C remains CLOSED / PASS. This E1 checkpoint did not deploy. No real
production title was prepared. Actual delete calls = 0; DB writes = 0; NAS
writes/deletes = 0; Jellyfin writes/refresh = 0; Discovery reconcile writes =
0; Hermes/VM122 calls = 0; subtitle generation = 0. Next: Stage13-E2 may deploy
the DRY-RUN endpoints for a read-only canary; actual deletion remains disabled.

## Stage13-E2 Permanent Delete DRY-RUN production deployment — 2026-09-28

Built and deployed exact source HEAD `ebd04178991659661efd416d0435e03e0ddc5584`
as `ghcr.io/ssikgun/missav-dlp-web:stage13e2-ebd0417`, image
`sha256:62c276b041a42a20a81fbbe925ff165f0b49a0674dff898fd5e2855f60afadef`.
The previous running app image was
`sha256:7f427ebf957180466c7fe0d56122dd5eddfc833f3919ab9527741d8a1399df19`.
Production Compose was rendered with the existing env and C2/C4/C6 overrides;
only the app image differed. Only `missav-dlp-web` was recreated. The app is
running with restart count 0; other service container IDs were unchanged.
Unauthenticated `/` still redirects to login and Library/status/prepare/
validate API requests remain 401. No credential or auth bypass was used.

The current read-only Discovery source was 182 present JAV holdings before
deployment and remained 182 afterward (182 distinct IDs, all `MATCHED`, no
duplicate IDs), rather than the E2 expected 177. This is recorded as a
pre-existing count discrepancy; no cause or timing is inferred. ADN-785 was
rechecked as one valid present canonical holding with no active subtitle job.
Using the deployed bounded manifest reader against only its exact canonical
title directory found 4 direct regular files totaling 3,528,183,972 bytes;
manifest identity SHA prefix `646a207fa39f`. The canonical media size/mtime
matched the holding. No symlink, special file, nested directory or entry
bound violation was found. Read-only state was KO `VALID` and Jellyfin
`RECOGNIZED`. This was an internal exact-folder reader canary, not a call to
the authenticated prepare API; no token was issued.

The production prepare/validate/replay HTTP canary was not run because no
existing authenticated same-origin HTTP/browser session was available. The
unauthenticated guard was verified, including form-style prepare rejection;
authentication was not bypassed. Therefore API prepare summary, `READY_FOR_COMMIT`,
and replay idempotency remain unverified in production. Source/runtime route
inspection confirms only prepare and validate routes are registered; there is
no delete commit endpoint. Deployed UI wiring contains prepare/validate only,
and no commit button. Fixture smoke remains the evidence for token expiry,
wrong identity, missing acknowledgement, drift and replay paths.

Deployed template/static checks passed for the Library page, prepare/validate
UI wiring, existing Library and transient Files stream adapters, and exactly
one shared video element. No authenticated browser harness is installed, so
`DELETE_DRYRUN_UI_VISUAL=PENDING_TEDDY`.

No rollback was performed. The E2 candidate remains deployed. Production write
audit: DB writes 0, NAS writes/deletes 0, Jellyfin write/refresh 0, Discovery
reconcile writes 0, Hermes 0, VM122 0, subtitle generation 0, permanent delete
0. The only production mutation was replacement of the web app image/container.
E2 is incomplete pending an authenticated same-origin prepare/validate/replay
canary and reconciliation of the observed 182-versus-177 holdings count before
claiming the requested production contract. Actual deletion remains disabled.

## Stage13-E2C delete prepare 403 diagnostics hotfix — 2026-09-29

Added bounded one-line diagnostics to the authenticated Library delete-intent
guard. Rejections now log the exact `invalid_request_boundary` or
`invalid_request_origin` code and a bounded subreason (`mimetype`,
`intent_header`, `origin_missing`, `scheme_mismatch`, `host_mismatch`, or
`cross_site`), with sanitized request/origin scheme and host, forwarded-header
presence/value, `Sec-Fetch-Site`, content type, method, intent and header value.
Cookie, session, authorization, token, body, query and client IP are not logged.
All authentication, JSON, intent, same-origin and `Sec-Fetch-Site` checks are
unchanged; no forwarded header is trusted by this change.

The Library UI now displays only allowlisted safe server error codes for
prepare and validate failures; unknown codes and raw server messages continue
to use the generic UI text. Prepare/validate success behavior and the disabled
actual-delete state remain unchanged.

Fixture smoke exercised invalid content type, wrong intent, missing Origin,
scheme mismatch, host mismatch, cross-site, and valid same-origin requests.
It checked exact subreason logs and verified cookie/session/token sentinel
values were absent. Library API/UI, delete DRY-RUN, File Management
navigation, subtitle status, Discovery UI, Python compilation and
`git diff --check` passed. Full Docker build passed from the isolated source
commit `22bb71edddf638e59f98eb4c945e31f204d47100`, excluding unrelated local
subtitle parser changes.

Deployed `ghcr.io/ssikgun/missav-dlp-web:stage13e2c-22bb71e`, image
`sha256:ab0a8281d6ecb7b81fa5851cd5e523059b44de74e3270a79cfd9c9a2e07d63dc`.
Only `missav-dlp-web` was recreated; the prior E2 image was retained as
rollback candidate. The app is running with restart count 0. `/login` returned
200, unauthenticated `/` redirected to login, Library and subtitle APIs
returned 401, and Library JS/CSS returned 200. No authenticated prepare was
retried by Codex. Token issue = 0 and actual delete = 0; no validate request,
Discovery reconcile, Jellyfin refresh, Hermes/VM122 call or subtitle generation
was invoked by this checkpoint.

Next: Teddy clicks `ADN-785 > 🗑️ 영구 삭제` once in the authenticated browser.
The safe UI code and application log should now identify the rejected guard
branch. Actual deletion remains disabled.

## Stage13-E2E trusted public-origin helper — 2026-09-29

Added a strict shared parser in `teddy_public_origin.py` and configured
`TEDDY_PUBLIC_ORIGIN` as the required app environment value in the canonical
production Compose file. The parser accepts only HTTP(S) origins with a host
and optional valid port; it rejects userinfo, non-root paths, query/fragment,
wildcards, malformed authorities and unsupported schemes. Canonical values
include scheme, normalized hostname/netloc and effective port, so default
ports normalize consistently.

The delete prepare/validate origin guard still requires authentication, JSON,
the exact intent header, a present same-origin Origin, and non-cross-site
`Sec-Fetch-Site`. It now compares the browser Origin to
`TEDDY_PUBLIC_ORIGIN`, and separately verifies the app-visible request Host
against that configured authority. The private `request.scheme` is not part
of the decision, allowing the established HTTPS-public/HTTP-private-proxy
shape. `X-Forwarded-Proto` and `X-Forwarded-Host` remain diagnostic only and
are not trusted. Missing or invalid configuration rejects closed with the
existing `invalid_request_origin` response and bounded diagnostic subreason.
No ProxyFix or domain-specific production source constant was added.

Fixture coverage passed for proxy-terminated HTTPS, scheme/host/port mismatch,
default and explicit port handling, missing/malformed/unsafe configuration,
forwarded-header spoofing invariance, cross-site and intent rejection, plus
successful prepare and validate-only responses. Both phases returned
`actual_delete_performed=false`; no delete/commit endpoint exists. Library
API, Library UI, File Management navigation, subtitle status and Discovery UI
smokes passed. Python compilation and `git diff --check` passed. The full
Docker image build passed as `missav-stage13e2e-smoke:f795bec-final`,
image `sha256:1edd1c4ea95e382bc884ff43d801695ec1ab543dc164e1d9ab33acf88be0f65b`.

No production environment file was changed and no image was deployed or
restarted. Production prepare/validate was not called. Actual delete = 0;
production DB writes = 0, NAS writes/deletes = 0, Jellyfin writes/refresh = 0,
Hermes/VM122 calls = 0, and subtitle generation = 0. Next: Stage13-E2F may
configure `TEDDY_PUBLIC_ORIGIN` in the production environment, redeploy only
the web app, and have Teddy retry the authenticated prepare/validate DRY-RUN.

## Stage13-E2F trusted public origin production deployment — 2026-09-29

The production environment previously had no `TEDDY_PUBLIC_ORIGIN` key.
Added exactly one entry with value
`https://downloader.ssikgun.com`, preserving the env file's existing owner,
mode and LF convention. Added the corresponding environment pass-through to
the production `missav-dlp-web` Compose service. No other env entry or
service configuration changed.

Built source HEAD `6e5fa88ce17ada4f277fcd8d4be8cc8f02cc1b6a` as
`ghcr.io/ssikgun/missav-dlp-web:stage13e2f-6e5fa88`, image
`sha256:9931fa76baff36984e2cef51f3de77c019236f538da1983582a8856188398cdc`.
The image carries OCI revision label
`6e5fa88ce17ada4f277fcd8d4be8cc8f02cc1b6a`. Only the `missav-dlp-web`
service was recreated with `--no-deps`. Its previous image,
`sha256:ab0a8281d6ecb7b81fa5851cd5e523059b44de74e3270a79cfd9c9a2e07d63dc`,
was retained as rollback candidate; rollback was not needed.

The app is running with restart count 0 and published port 58000 unchanged.
Gluetun and both browser container IDs remained unchanged. Compose render
showed the only app changes were the image and public-origin environment;
ports, network, data mounts, read-only Discovery/rollout DBs, NAS SSH
credential mount and Jellyfin key mount stayed unchanged. Runtime env check
matched the exact configured value. The deployed helper parsed it as
`scheme=https`, `host=downloader.ssikgun.com`,
`effective_port=443`, valid=true.

Unauthenticated `/login` returned 200, `/` redirected to login,
`/api/library` and delete prepare returned 401. Library, Discovery and
subtitle status assets returned 200. Runtime route inspection found prepare
and validate only; no delete/commit route is registered. No authenticated
prepare or validate was called and no session was created or copied.

Production writes: DB 0, NAS write/delete 0, Jellyfin write/refresh 0,
Discovery reconcile 0, Hermes 0, VM122 0, subtitle generation 0, permanent
delete 0. The only production mutations were the public-origin env/config
setting and replacement of the web app image/container. Next: Teddy performs
the authenticated ADN-785 prepare and validate-only flow in the browser.
Actual deletion remains disabled.

## Stage13-E2 authenticated production DRY-RUN closure — 2026-09-29

Teddy completed the authenticated production UI DRY-RUN for ADN-785. Prepare
reported 4 managed files totaling approximately 3.3 GB, manifest SHA prefix
`646a207fa39f`, Korean subtitle present and Jellyfin recognized. Validate
returned `READY_FOR_COMMIT`. Actual deletion remained disabled and no
production file was deleted.

Stage13-E2 is CLOSED / PASS for the prepare/validate DRY-RUN contract.
ADN-785 was only the DRY-RUN subject; this outcome does not approve it or any
other title for a future real deletion canary. Stage13-F1 implementation
continues offline with its feature gate disabled and production delete count
remaining zero.

## Stage13-F1 one-title permanent delete implementation — offline PASS, 2026-09-29

Stage13-E2 remains CLOSED / PASS for authenticated prepare/validate DRY-RUN.
Teddy's ADN-785 observation (4 managed files, approximately 3.3 GB,
manifest prefix `646a207fa39f`, KO present, Jellyfin recognized,
`READY_FOR_COMMIT`) did not approve ADN-785 or any other work for actual
deletion.

F1 adds `POST /api/library/<dvd_id>/delete/commit`, plus durable
`/delete/reconcile` and `/delete/resume` recovery paths. Actual mutation is
fail-closed behind `TEDDY_LIBRARY_DELETE_ENABLED`; missing/false disables it.
Commit requires authenticated JSON, the existing destructive intent and
trusted public-origin guard, a validated short-lived DVD-bound token, exact
typed DVD-ID, acknowledgement and the final phrase, then a fresh canonical
holding/source fingerprint and exact manifest match.

The mutator uses the existing hardened dedicated NAS SSH transport and sends
bounded JSON to a fixed Python helper. It lstat-checks the JAV root, family,
title directory and direct entries; permits only exact regular-file entries
matching type, device, inode, size and mtime; unlinks those entries one by
one; and rmdirs only the now-empty exact title directory. It never recurses,
uses a glob, removes a family parent, or uses a CT108 JAV mount. Manifest SHA
identifies canonical manifest metadata, not file contents.

Durable audit/recovery state is SQLite at
`/downloads/teddy-library-delete-provenance.sqlite3`, on the existing
persistent `/downloads` storage. It records operation/DVD identity,
source fingerprint, manifest metadata, timestamps, removed/remaining entry
names, bytes/counts and result/reconciliation states; no token, session,
secret, subtitle body or absolute NAS path is stored. Partial operations can
resume only against the original manifest; post-restart recovery re-inventories
the exact title folder and accepts only the exact expected remaining subset.
After NAS completion, Discovery marks that exact holding `present=0`; then
Jellyfin is reconciled by exact-path GET, targeted item refresh, and GET
verification. Failures remain `RECONCILE_PENDING` without reversing deletion.

The UI requires the existing prepare/validate sequence followed by a separate
exact DVD-ID, acknowledgement, fixed phrase and explicit commit action. The
commit controls remain disabled unless prepare reports the server feature gate
enabled, and the button disables on first click. API replay does not repeat a
completed mutation. Offline fixtures cover gate/auth/origin/token/identity
failures, manifest and filesystem drift, symlink/special/nested rejection,
exact delete boundaries, partial and process-restart recovery, provenance,
Discovery/Jellyfin success and pending recovery, response secrecy and UI
confirmation. Library/API, delete DRY-RUN, File Management, subtitle status,
Discovery and full Docker build checks passed.

Production deploy = NO; production `TEDDY_LIBRARY_DELETE_ENABLED` was not set
or changed. Production DB writes = 0, NAS writes/deletes = 0, Jellyfin
refresh/write = 0, Discovery reconcile writes = 0, Hermes/VM122 = 0,
subtitle generation = 0, actual permanent deletes = 0. Next: Stage13-F2
production deploy/preflight only; keep the gate disabled and do not perform an
actual canary deletion without Teddy's separate explicit approval.

## Stage13-F2A gated production deploy / destructive path preflight — INCOMPLETE, 2026-09-29

Deployed exact source `63fc052e2ad85f75646bdb500640fcb828a561e4` as
`ghcr.io/ssikgun/missav-dlp-web:stage13f2a-63fc052`, image ID
`sha256:e6a5d1f428e3b745a1605017cb89fa09c14a24701fa99f50dfbe26e7abc34b3f`.
Before deploy the rollback image was `sha256:9931fa76baff36984e2cef51f3de77c019236f538da1983582a8856188398cdc`.
Only `missav-dlp-web` was recreated (`--no-deps`); Gluetun and browser
container IDs remained unchanged. The app is running with restart count 0,
port 58000 and its prior network/mount boundary. No rollback was needed.

`TEDDY_LIBRARY_DELETE_ENABLED` is absent from production env, rendered Compose,
and runtime; runtime `delete_enabled` is false. Source order gates commit,
reconcile and resume before provenance creation, holding write or NAS/Jellyfin
mutator calls. Existing F1 offline tests cover `delete_disabled`. No
production authenticated prepare, validate, commit, reconcile or resume was
called. `/login` returned 200, `/` redirected to login, `/api/library` and an
unauthenticated commit returned 401, and Library JS/CSS returned 200.

Provenance uses `/downloads/teddy-library-delete-provenance.sqlite3` (no
production record was created). The path is on persistent host bind
`/opt/missav-dlp-web/work:/downloads`, RW, not tmpfs; its parent exists and
has writable capability. `TEDDY_LIBRARY_DELETE_PROVENANCE_DB` is unset.

Production `TEDDY_DISCOVERY_DB=/discovery/teddy-discovery.sqlite3` maps to
`/opt/missav-dlp-web/discovery/teddy-discovery.sqlite3:ro`. F1 passes this
same `db_path` into `reconcile_discovery_holding()`, which opens it with
SQLite `mode=rw` and conditionally updates exact `holding_id`/DVD/path/
identity from `present=1` to `present=0`. This cannot write through the
current mount: `DISCOVERY_RECONCILE_RW_PATH=BLOCKED_BY_READ_ONLY_MOUNT`.

No existing narrow writer for this exact post-delete lifecycle was found.
Organizer publish updates holdings to `present=1`; Discovery import and the
Stage10 JAV reconcile apply path perform broader inventory reconciliation and
are not suitable request-time single-title writers. The live DB reports
`journal_mode=wal` and has WAL/SHM sidecars. Therefore a second path alias to
the same DB must not be enabled until WAL/SHM coordination is proven: SQLite
sidecar paths are derived from the opened path. Proposed safe follow-up is a
small host-side narrow writer over a local Unix socket, opening the one
canonical DB path and accepting only exact holding identity/fingerprint data;
it performs a parameterized conditional `present=0` update under the shared
writer coordination boundary. The app's existing read DB mount stays RO and
only the delete reconcile caller can use that writer. No helper, RW mount, or
DB write was added in F2A.

The production NAS transport is configured for host `192.168.1.201`, user
`ssikgun`, with key and known_hosts paths under the read-only
`/run/secrets/teddy-nas-transfer` mount. The mutator's library root remains
`/volume1/video/video2/JAV`; F1 uses exact manifest unlink/rmdir, not `rm -rf`,
globs or recursion. No NAS SSH mutation was invoked. Jellyfin reconciliation
uses GET exact-path lookup, targeted API refresh and verification; its API key
mount is RO. No Jellyfin request/write/refresh was performed.

Read-only current holdings snapshot: `storage_root='jav' AND present=1` = 184.
This is a point-in-time count, not a fixed invariant. The provenance path
preflight passed, but safe Discovery reconciliation is a required canary
prerequisite and remains blocked; Stage13-F2A is therefore
`INCOMPLETE — APP_DEPLOYED / DELETE_GATE_DISABLED / DISCOVERY_RECONCILE_BLOCKED`.
Keep this image deployed and gate disabled. Production DB/NAS/Jellyfin writes,
provenance records, subtitle generation, Hermes/VM122 calls and actual deletes
were all 0. Next: implement and fixture-verify the narrow canonical-path
Discovery writer, then separately deploy/preflight it before any real canary.

## Stage13-F2B host-side Discovery reconcile writer — PASS, 2026-09-29

Implemented `teddy_library_discovery_writer.py`: a local Unix-domain socket
server/client with only `health`, `preflight_holding` and `mark_absent` ops.
The newline-delimited UTF-8 JSON frame is capped at 8 KiB, responses at 4 KiB,
unknown fields/operations are rejected, and socket startup refuses a symlink
parent or any pre-existing socket path. The runtime directory contract is
0750 and socket mode 0660; deployment must align the app container's connect
GID with the service group after checking actual runtime identities.

The host service receives the canonical Discovery DB and persistent provenance
DB paths only through administrator-controlled CLI configuration; requests
cannot provide a DB/path/SQL/field value. It reads provenance in SQLite RO /
query-only mode and requires exact operation/DVD/holding/fingerprint identity,
`nas_delete_complete=1`, empty remaining entries, complete exact manifest
removal counts, and a permitted reconciliation state. Discovery writes use
the canonical host DB path, SQLite `mode=rw`, `busy_timeout`, `BEGIN IMMEDIATE`
and one conditional `holdings.present=1 -> 0` update matching holding ID,
DVD-ID, canonical relative path, storage root, parse status, size and mtime.
No WAL mode change or second DB alias is introduced. Same-operation replay is
idempotent when its durable provenance marks Discovery reconciled; another
operation cannot claim an already-absent row.

The web app now defaults to `TEDDY_LIBRARY_DELETE_DISCOVERY_WRITER_SOCKET` and
has no direct RW fallback. Commit and partial-resume paths must receive
`READY` from `preflight_holding` before provenance enters `COMMITTING` and
before the NAS mutator can run. The existing injected direct reconciler remains
available only to offline fixtures. A full fixture exercised socket preflight,
exact fixture deletion, exact holding reconciliation and Jellyfin fixture
completion; unavailable-writer preflight left the NAS fixture untouched and
created no provenance record. Writer protocol, malformed/oversized requests,
identity/provenance failures, conditional update, unrelated-row preservation,
DB-busy behavior, socket permissions, restart replay and no-path/no-token
responses passed. Existing F1 partial/retry, E1 prepare/validate, Library API
and UI, File Management, subtitle status and Discovery smokes passed; Python
compile, `git diff --check` and the full Docker image build passed.

No writer service/socket was installed or created on production. The existing
systemd deployment convention was inspected; F2C must first settle the host
service code install path and service user/group against the web container's
actual UID/GID, then install the unit/runtime directory and bind the socket
directory into only the web app as connect-only/read-only. Configure
`TEDDY_LIBRARY_DELETE_DISCOVERY_WRITER_SOCKET=/run/teddy-library-discovery-writer/writer.sock`;
keep `/discovery/teddy-discovery.sqlite3:ro` and feature gate disabled. The
host writer CLI requires explicit `--discovery-db`, `--provenance-db`, and
`--socket` arguments. No production deploy, service install, feature-gate
change, provenance record, DB write, NAS write/delete, Jellyfin refresh/write,
subtitle generation, Hermes/VM122 call or actual delete occurred. Next:
Stage13-F2C production writer install/socket bind and disabled-gate preflight
only; no one-title deletion.

## Stage13-F2C host-side Discovery writer install and disabled-gate preflight — PASS, 2026-09-29

Exact source `09a3a89bac6af910ca3543f8c076bb0f54e2cb41` was exported to the
immutable host release directory
`/opt/missav-dlp-web/teddy-library-discovery-writer/releases/09a3a89bac6af910ca3543f8c076bb0f54e2cb41/`.
The snapshot contains only the writer and its import dependencies, is
root-owned/read-only, and includes a `SOURCE_COMMIT` marker matching the
expected revision. Host Python is `/usr/bin/python3` (3.13.5); import passed.

The host Discovery directory and DB/WAL/SHM are root-owned mode 0700/0600;
web app also runs as UID 0. A non-root writer cannot safely access them without
changing existing ownership/modes, so F2C retained root and applied a dedicated
primary group `teddy-library-discovery-writer` (GID 988) for the socket. The
systemd unit is `teddy-library-discovery-writer.service`, active/enabled,
`NRestarts=0`, running as root:that group. Sandbox has `NoNewPrivileges`,
`PrivateTmp`, `ProtectSystem=strict`, only the Discovery directory writable,
the provenance work directory read-only, `RestrictAddressFamilies=AF_UNIX`,
and an empty capability set. RuntimeDirectory is systemd-managed at
`/run/teddy-library-discovery-writer`, mode 0750; socket is root:group mode
0660. Controlled restart removed/recreated the runtime socket, changed the
service PID, and host health returned `READY` before and after restart.

Production Compose now passes the socket path, adds supplementary GID 988 to
only the web app, and bind-mounts the socket directory read-only at the same
container path. Rendered config retains port 58000, default network, existing
storage mounts, and `/discovery/teddy-discovery.sqlite3:ro`. The running web
container confirms the socket and Discovery mounts are both read-only and its
supplementary group includes 988; container-side Unix socket health returned
`READY`, proving connect works over the read-only bind. Only
`missav-dlp-web` was recreated; Gluetun and both browser container IDs stayed
unchanged.

Exact F2B image built and deployed: source
`09a3a89bac6af910ca3543f8c076bb0f54e2cb41`, tag
`stage13f2c-09a3a89`, image ID
`sha256:40d68b117add00b0dfa85748780d49c3578e670af42d11aa2ae9dfda805dc787`.
App is running, restart count 0. `/login` and Library JS/CSS returned 200,
unauthenticated `/` redirects to login and `/api/library` returns 401.
`TEDDY_LIBRARY_DELETE_ENABLED` remains missing/disabled in Compose and runtime.

Read-only exact holding probe used ADN-785 / holding 141, canonical MATCHED
identity and its source fingerprint. Container-side `preflight_holding`
returned `READY`; the writer performed `BEGIN IMMEDIATE`, exact SELECT and
ROLLBACK. Before/after current `jav AND present=1` count remained 184 and the
target row identity remained unchanged. No provenance DB/file existed before
the probe and none was created. Its parent `/opt/missav-dlp-web/work` is
root-owned 0755; a future container-created root:root 0600 provenance DB is
readable by the root writer, while systemd exposes the work path read-only.

No `mark_absent`, authenticated commit, reconcile or resume call was issued.
Discovery content writes = 0, provenance record writes = 0, NAS writes/deletes
= 0, Jellyfin refresh/write = 0, subtitle generation = 0, Hermes/VM122 = 0,
actual permanent deletes = 0. Next: Stage13-F2D final pre-canary safety
preflight only; keep the delete gate disabled and do not delete a title.

## Stage13-F2D final permanent-delete safety preflight — INCOMPLETE, 2026-09-29

Source preflight started at `06a75d42ca350e069d7a87b3a45e52241923c91a` on
`teddy-subtitle-stage11`, clean and equal to the server branch. No source code
divergence was found. The running web app remains F2C image
`sha256:40d68b117add00b0dfa85748780d49c3578e670af42d11aa2ae9dfda805dc787`,
running with restart count 0; no service was recreated.

F2C socket wiring had been applied to the production compose but was absent
from the repository deployment compose. Both
`docker-compose.gluetun.yml` and `/opt/missav-dlp-web/compose.yaml` now define
`TEDDY_LIBRARY_DELETE_DISCOVERY_WRITER_SOCKET=/run/teddy-library-discovery-writer/writer.sock`,
the host-to-container runtime directory bind as read-only, supplementary
writer GID 988, and `TEDDY_LIBRARY_DELETE_ENABLED=${TEDDY_LIBRARY_DELETE_ENABLED:-false}`.
Sanitized renders of both compose files agree: gate `false`, public origin
`https://downloader.ssikgun.com`, Discovery DB mounted `:ro`, writer socket
directory mounted `:ro`. The currently running container still has the gate
variable missing; application evaluation is fail-closed (`false`). Its
effective state was not enabled. No compose up/recreate was run.

Writer release remains the immutable
`/opt/missav-dlp-web/teddy-library-discovery-writer/releases/09a3a89bac6af910ca3543f8c076bb0f54e2cb41/`,
service `teddy-library-discovery-writer.service` active/enabled, root-owned
with the restricted `teddy-library-discovery-writer` socket group, PID
978934, no restart loop. Socket is a Unix socket, root:group mode 0660;
runtime directory is 0750. Existing F2C controlled restart evidence remains
valid. Host and container `health` returned `READY`. The exact read-only
probe of ADN-785 / holding 141 returned `READY`; `present=1` and current
holdings count remained 184. This connectivity probe is not canary approval.

Current Discovery snapshot: 184 present JAV holdings, 184 unique DVD-IDs,
0 duplicates and 0 canonical/parse mismatches. Organizer job rows currently
all report `COMPLETED` (184); Stage12 `RUNNING`/`GENERATED` rows currently
number 0. These point-in-time counts do not replace a per-title guard.
Source review found no commit/resume guard that checks the requested DVD-ID
against active organizer/completion work and active subtitle generation.
Therefore `CANARY_BLOCKER=ACTIVE_JOB_GUARD_MISSING` and
`CANARY_READY=NO`; do not enable the gate or perform a canary until a
source fix adds the target-specific fail-closed collision check.

Static ordering review confirms the configured gate and validated token are
checked before mutation; exact current identity/manifest and Discovery writer
`preflight_holding` precede durable `COMMITTING` provenance and the NAS
mutator, including partial/uncertain resume. Production reconciliation uses
the socket writer only; direct SQLite reconciliation is available only when
explicitly injected by offline fixtures, with no production RW fallback.
The writer independently reads durable provenance before its exact conditional
`present=1 -> 0` update. The NAS mutator uses exact manifest `lstat` checks,
per-file `unlink`, then removes only the verified empty title directory; it
does not use recursive delete, globs or arbitrary paths. Partial recovery is
durable and scopes retries to the original manifest/remaining entries.
Jellyfin reconciliation uses API GET by exact path and targeted item refresh
after Discovery succeeds; it does not edit the Jellyfin database, and failure
leaves reconciliation pending rather than reversing NAS deletion.

Offline Discovery writer and F1 delete/recovery fixture smokes passed. No
production prepare/validate/commit/resume/reconcile request was made.
Discovery writes = 0, provenance writes = 0, NAS writes/deletes = 0,
Jellyfin refresh/write = 0, subtitle generation = 0, Hermes/VM122 calls = 0,
actual permanent deletes = 0. Production web image remains unchanged.
Next: implement and fixture-test the per-DVD active-job collision guard,
then repeat F2D preflight before Teddy selects a canary title.

## Stage13-F2E target activity guard — INCOMPLETE FOR CANARY, 2026-09-29

F2D identified `ACTIVE_JOB_GUARD_MISSING`. This checkpoint adds a generic,
read-only target activity guard in `teddy_library_delete_activity.py`; no
production deploy or restart was performed. The F2C production app remains on
its prior image with `TEDDY_LIBRARY_DELETE_ENABLED` missing/effectively false.
Actual delete remains disabled.

Organizer source evidence: `organizer_jobs` has no schema CHECK constraint;
`organizer_apply` creates `RUNNING`, records `PUBLISHED` after publishing the
holding and before source cleanup, then records `COMPLETED`. Failed operations
record `FAILED`; known incomplete recovery states include `CLEANUP_PENDING`
and `DB_FAILED_AFTER_PUBLISH`. The guard treats `RUNNING` and `PUBLISHED` as
active, `COMPLETED` and `FAILED` as terminal, and incomplete/unknown values as
`ACTIVITY_STATE_UNAVAILABLE` (fail-closed). Queries are exact `WHERE dvd_id=?`
against the read-only Discovery DB.

Subtitle source reuses `teddy_subtitle_status.py` active statuses and heartbeat
parser/freshness contract. A target rollout row in `RUNNING` or `GENERATED`
blocks even if heartbeat is stale. A fresh `RUNNING` heartbeat blocks only
when `current_dvd_id` matches the target; a fresh heartbeat naming another
DVD-ID does not. A stale valid heartbeat alone does not block. Missing
heartbeat is allowed when durable state is readable; unreadable/malformed
heartbeat, invalid fresh state, or rollout DB failure returns
`ACTIVITY_STATE_UNAVAILABLE`. Future subtitle controllers can be added as
providers without changing delete-route logic.

Commit performs target checks after final holding/manifest validation and
again after writer preflight, before provenance `COMMITTING` and NAS mutation.
Partial commit retry and incomplete resume use the same two checks before
resuming provenance/mutator work. `RECONCILE_PENDING` recovery remains outside
the activity guard so completed NAS deletion can reconcile. Safe API outcomes
are `delete_target_active` and `delete_activity_unavailable`; no job/session
or heartbeat details are returned. Fixture checks confirmed active/unavailable
before the first check or between checks causes zero NAS mutator calls and no
new provenance operation; idle controls continue through the existing fixture
path; active partial resume is blocked; already-completed reconciliation is
not blocked.

`SHARED_PER_TITLE_LOCK=UNAVAILABLE`. Organizer has a database writer flock,
completion orchestration has a separate global operation lock, and Stage12
has its own singleton runner lock. None is a shared per-title lock held by
these producers and the web deletion route. Double activity checks close the
writer-preflight interval but leave a TOCTOU window after the second check and
before the first exact unlink. Therefore `CANARY_READY=NO`; do not enable the
gate or select/delete a canary until this cross-worker race is closed or a
separately verifiable operational exclusion is approved.

Offline target-activity, writer, prepare/validate, commit/partial-recovery,
Library API/UI, File Management navigation, subtitle status and Discovery
smokes passed. Python compile, `git diff --check`, and full local Docker build
passed. Production deploy = NO; production gate remains false/effectively
disabled; production DB/NAS/provenance/Jellyfin mutations = 0, subtitle
generation/Hermes/VM122 = 0, actual delete = 0. Next: resolve the shared
per-title exclusion/race, then repeat F2D final preflight before any canary.

## Stage13-F2I unexpected media retry forensic — INCOMPLETE / CANARY BLOCKED, 2026-09-29

Source/runtime identity was checked read-only: checkout and remote branch are
both `807d400999febdb8e13a5d70a624f75477785d16`; production web image remains
`sha256:bac75af6716cd7a0e33aa671b90f9386926d8dc93f64dba201caa6494283e404`.
The web app is running with delete gate false. The completion timer remains
enabled but inactive; its last trigger was 2026-09-29 12:31:56 KST and its
one-shot service exited successfully at 12:31:57 KST. No timer/service action
was performed during this forensic.

The bounded incident journal reports completion `total=0`, `eligible=0`,
`applied=0`, media reconciliation `0`, and one retry attempted, zero completed,
one failed. The exact media state row is `media_job_id=174261`,
`dvd_id=MFCS-085`, status `FAILED`, `attempt_count=17161`, updated at
`2026-09-29T03:31:57Z`. The stored error was examined without printing its
contents; it did not match the pinned runtime's known safe error literals, so
the safe classification remains `UNCLASSIFIED_ERROR` and
`FAILURE_STAGE=FAILURE_STAGE_UNKNOWN`.

The current exact Discovery holding is holding 165, `MFCS-085`,
`MFCS/MFCS-085/MFCS-085.mp4`, present=1, discovered by `completion-stage9`,
size 1,467,881,427 bytes and mtime_ns 1788865655288182673. A bounded direct
listing of only that canonical title directory found the regular media file
and `MFCS-085.ko.srt`; the media size/mtime matches the holding. No current
NFO/poster sidecar or `.teddy-stage9-meta-*.partial` entry was found. This is
current-state evidence only, without an incident-time baseline; therefore
`NAS_METADATA_SIDE_EFFECT=UNKNOWN`.

Jellyfin was queried GET-only. One current item matches the exact canonical
media path. This does not establish whether this invocation sent its notify
POST, so `JELLYFIN_SIDE_EFFECT=UNKNOWN`.

Pinned F2F source audit: `run_retryable_media_jobs()` marks each selected job
RUNNING/increments attempts, invokes its processor, then records FAILED on an
exception. The completion runner calls this retry path after the separately
locked completion `process_one()` loop. The retry path does not acquire the
shared title lock; neither `run_media_pipeline()` nor its NAS metadata publish
and Jellyfin notify stages are within that per-title lock. Thus
`MEDIA_RETRY_TITLE_LOCK=NO`. FAILED rows remain retryable and the runner has no
per-job retry ceiling/backoff, so resuming the timer risks repeatedly running
this same row. `COMPLETION_TIMER_SAFE_TO_RESUME=NO`.

The separate `teddy-discovery-jav-reconcile-apply.service` is an inactive,
manual one-shot with no apply timer attached (the scheduled reconcile unit is
report-only). Its pinned launcher currently targets the old mutable
`/opt/missav-dlp-web/stage9-runtime`; apply performs a bounded remote library
reconciliation and can update Discovery holdings under the global
`teddy-discovery-jav-library-operation.lock`. It has no per-title lock. The
delete path does not take that global lock, so it is not mutual exclusion with
delete. Freeze manual apply around any future delete canary until an explicit
exclusion contract is implemented:
`RECONCILE_APPLY_LOCK_VERDICT=NEEDS_SEPARATE_OPERATIONAL_FREEZE`.

No retry, repair, reconcile apply, prepare/validate/commit/resume, NAS action,
Discovery write, provenance write, Jellyfin write/refresh, subtitle work,
Hermes/VM122 call, or delete occurred in this checkpoint. Current completion
timer is still inactive. `CANARY_READY=NO`; blockers are missing shared title
exclusion on media retries, unknown incident side-effect stage, unbounded
retry behavior, and the manual reconcile-apply exclusion gap. Next: implement
and offline-test a retry-specific title-lock boundary with bounded retry
semantics, then define the reconcile-apply/delete exclusion and repeat a
read-only production preflight. Do not resume the completion timer meanwhile.

## Stage13-F2J media retry exclusion and bounded policy — PASS, source/fixture only, 2026-09-29

F2I incident evidence remains unchanged: media job 174261 / `MFCS-085` is
FAILED at 17,161 attempts; its exact failure stage and incident-time NAS
metadata/Jellyfin effects remain UNKNOWN. No production retry or repair was
performed.

`teddy_discovery_media_jobs.py` now uses the existing
`teddy_title_exclusion.try_acquire_title_lock()` with
`TEDDY_TITLE_LOCK_DIR`. The retry acquires the title lock before conditional
RUNNING transition and retains it through processor completion and durable
COMPLETED/FAILED update. This covers NAS metadata publication and Jellyfin
notification in the existing media pipeline. BUSY returns
`HELD_TITLE_BUSY`; missing/invalid/unavailable lock infrastructure returns
`TITLE_LOCK_UNAVAILABLE`. Either outcome leaves the media row and attempt
count unchanged and never calls the processor.

Retry policy uses existing `status`, `attempt_count`, and `updated_at`
columns; no schema migration was added. Defaults are max attempts 5, FAILED
backoff 3,600 seconds, and RUNNING stale threshold 7,200 seconds. PENDING is
immediately eligible below the attempt cap. FAILED is eligible only after the
backoff; RUNNING is eligible only after the stale threshold; malformed or
timezone-naive required timestamps are held. COMPLETED is never retried and
at/above-cap jobs are EXHAUSTED. Thus the known 17,161-attempt fixture maps to
EXHAUSTED / not automatically eligible. There is no production manual retry
override in this change.

After acquiring the title lock, the runner starts the existing short media
writer transaction, rereads the row and re-evaluates eligibility, then uses a
conditional UPDATE on job ID, DVD-ID, expected status, attempt count, and
updated_at. A changed/deleted row is held as `HELD_CONFLICT`; processor is not
called. Lock order is title lock then media writer lock; no path was found
that holds the media writer lock while acquiring a title lock. The media
pipeline stage order itself is unchanged.

Fixture coverage passed for retry eligibility/backoff/stale/exhaustion,
malformed timestamps, title-lock BUSY/unavailable, lock held through
processing/final state, exception release, distinct-title progress, and
candidate row status/attempt/timestamp/removal races. Existing title-lock
process tests confirmed same-title BUSY, different-title parallelism and
process-exit release. Existing delete commit fixture confirmed a same-title
holder produces `delete_target_busy` before NAS mutation.

The broad `teddy-discovery-jav-reconcile-apply.service` remains unchanged.
It is a manual one-shot using the global operation lock, which delete does
not share. Therefore `CANARY_RECONCILE_APPLY_FREEZE_REQUIRED=YES`: during a
future actual delete canary, verify the apply service inactive, verify no
related process is running, and prohibit the supported apply launcher until
the destructive window ends. The exact production freeze procedure still
requires a read-only deployment/preflight checkpoint.

Offline media jobs/pipeline/publish, completion runner/media/orchestrator,
organizer, title exclusion, Stage12 batch/bulk/rollout/retry, F1 delete commit,
activity guard, Discovery writer, E1 prepare/validate, Library API/UI,
File Management navigation, subtitle status, Discovery, Python compilation,
`git diff --check`, and full Docker image build passed. The initial system
Python attempts for Flask-dependent smokes were rerun successfully in the
built Docker runtime; Stage12 retry smoke passed in its required
`/opt/stage11-stt-venv` interpreter.

Production deploy = NO. Completion timer remains inactive/enabled and was not
started; delete feature gate remains false. Production media/Discovery/
provenance DB writes, NAS writes/deletes, Jellyfin notify/refresh, organizer
publish, Stage12 processing, Hermes/VM122 calls, and actual delete = 0.
`MEDIA_RETRY_TITLE_LOCK=YES`, `MEDIA_RETRY_BOUNDED=YES`,
`MFCS085_AUTOMATIC_RETRY_ELIGIBLE=NO`,
`CANARY_RECONCILE_APPLY_FREEZE_REQUIRED=YES`, and
`COMPLETION_TIMER_SAFE_TO_RESUME=NO` because this change is not deployed.
Next: deploy the new pinned completion runtime, then read-only inspect eligible,
exhausted and backoff-held counts while leaving the timer stopped; repeat
canary safety preflight. No canary title is approved by this result.

## Stage13-F2K bounded media runtime rollout and read-only canary preflight — PASS / CANARY_READY=YES, 2026-09-29

The exact source commit `705bf9e700156d88523babfad15861a5faee9ff2` is
installed at immutable, root-owned mode-0555 release
`/opt/missav-dlp-web/stage9-runtime/releases/705bf9e700156d88523babfad15861a5faee9ff2/`.
It contains the 24 project-local Python modules in the prior completion runtime
closure, not a repository copy. Every installed module was SHA-256 compared
against `git show 705bf9e...:<path>`; all matched. The release marker identifies
the exact commit. The required media jobs, title exclusion, completion runner,
and completion orchestrator blobs matched. Offline imports and media jobs,
completion runner, and process-level title-lock smoke ran with the new release
and `/usr/bin/python3`; all passed.

The old completion wrapper was preserved byte-for-byte at
`/usr/local/sbin/teddy-completion-stage9-runner.backup-26c8657d4bd5c5b767f2f8eb474a80ff9121a150`.
The wrapper was atomically switched to the new release without executing it.
It sets `TEDDY_TITLE_LOCK_DIR=/opt/missav-dlp-web/title-locks`, sets
`PYTHONPATH` only to the new release, and retains the existing runner arguments.
`bash -n` passed. The systemd completion service defaults to root:root
(uid/gid 0:0), `/usr/bin/python3`, and imports from the exact 705 release.
The source tree `/opt/missav-pwa-subtitle-stage11` is not the runtime import
path; no old release path is added to `PYTHONPATH`.

Production media state was opened with SQLite `mode=ro` and
`PRAGMA query_only=ON`; no initializer or runner was called. Across the 20
PENDING/FAILED/RUNNING rows, the new pure policy classifies ELIGIBLE=19,
HELD_BACKOFF=0, HELD_FRESH_RUNNING=0, HELD_INVALID_TIMESTAMP=0,
HELD_INVALID_STATE=0, EXHAUSTED=1. Overall media statuses are COMPLETED=34,
PENDING=19, FAILED=1, RUNNING=0. The exact `MFCS-085` row remains job 174261,
FAILED, attempt_count=17161, and classifies EXHAUSTED. Source/fixture semantics
skip EXHAUSTED rows before lock acquisition, conditional RUNNING update, or
processor call. `MFCS085_AUTOMATIC_RETRY_ELIGIBLE=NO`.

Runtime title-lock verification used the pinned release Python on host and the
running web container at `/run/teddy-title-locks`. The host path is
`/opt/missav-dlp-web/title-locks`; the bind mount is the same host-backed
RW directory. For `ADN-785`, web-held → pinned-host attempt returned BUSY and
pinned-host-held → web attempt returned BUSY. After release both sides
acquired successfully. While the host held `ADN-785`, the web acquired
`MFCS-085`, confirming per-title concurrency. Host and container observed the
same regular lock-file device/inode (1796:548311), mode 0600. The shared root
is mode 0750 root:root. These are connectivity probes only, not a canary-title
selection.

Static audit confirms retry policy eligibility is evaluated before lock
acquisition; title lock is acquired before conditional RUNNING transition;
processor and final durable state update remain inside the title-lock scope.
The processor calls the unchanged media pipeline, whose metadata publish and
Jellyfin notify stages therefore remain locked. The title lock is outer to the
media-state writer transaction; no media writer-lock-held path was found that
then acquires a title lock. Organizer/completion still acquires title lock
before the global operation lock. `MEDIA_RETRY_LOCK_ORDER=PASS`.
The web container still has `TEDDY_TITLE_LOCK_DIR=/run/teddy-title-locks`,
`TEDDY_LIBRARY_DELETE_ENABLED=false`, Discovery DB mounted read-only, and
writer health READY. The existing delete commit/resume path uses the same
per-title primitive; no delete endpoint was called.

The completion timer is enabled but inactive; completion service is inactive.
No start/restart, service run, timer restoration, or daemon reload occurred.
`COMPLETION_TIMER_POLICY_READY=YES`; `COMPLETION_TIMER_RESUMED=NO`.
The separate `teddy-discovery-jav-reconcile-apply.service` is inactive and is
a manual one-shot with no apply timer. Its current wrapper/runtime target is
the old `/opt/missav-dlp-web/stage9-runtime` tree; its reconciliation source
uses the global operation lock
`/run/lock/teddy-discovery-jav-library-operation.lock`. The scheduled
`teddy-discovery-jav-reconcile.timer` points to report-only service, not apply.
Using the exact new runtime `operation_lock()` primitive in separate processes,
a short lock-only probe returned ACQUIRED for the holder, BUSY for a second
process while held, and ACQUIRED after release. No reconcile service ran.
Therefore `CANARY_RECONCILE_FREEZE_READY=YES`.

Frozen actual-canary operational procedure: (1) confirm completion timer
inactive; (2) confirm reconcile-apply service inactive and no related process;
(3) hold the global operation lock with a no-I/O freeze holder; (4) verify the
holder; (5) run target-specific activity and title-lock preflight; (6) keep the
freeze holder through the delete/reconciliation window; (7) confirm Discovery
and Jellyfin reconciliation, gate false, then release the holder; (8) decide
timer resumption separately. The lock holder performs no DB/NAS/Jellyfin I/O
and is short-lived in this checkpoint. This canary-only freeze does not change
normal global serialization.

Current read-only activity snapshot: organizer active=0; Stage12
RUNNING/GENERATED=0; heartbeat is present but stale (`COMPLETE`, no current
DVD-ID). No Stage12 systemd/cron automatic launcher was found. Current present
JAV holdings=184, unique DVD-ID=184, duplicates=0, canonical/parse mismatches=0.
No active conflicting job was observed. Eligible pending media jobs remain
stopped with the completion timer.

The F2I incident remains historically unresolved: its failure stage,
NAS metadata side effect, and Jellyfin side effect are still UNKNOWN, not
silently cleared. Per the F2K decision rule, that historical uncertainty does
not itself block a different future canary now that the failed row is
EXHAUSTED and bounded runtime/lock/freeze controls are verified.

`CANARY_READY=YES`. The deployed web app image remains
`sha256:bac75af6716cd7a0e33aa671b90f9386926d8dc93f64dba201caa6494283e404`;
delete feature gate=false. Production mutation was limited to the immutable
completion runtime install, wrapper backup/atomic switch, and lock-only
probes. Media/Discovery/provenance DB writes, NAS metadata/delete, organizer
publish, Jellyfin notify/refresh, Stage12 work, delete commit/resume/reconcile,
Hermes/VM122 calls, and actual permanent delete = 0. Next: stop code changes
and ask Teddy to select one intended canary title. Require separate final
irreversible confirmation immediately before any actual delete; do not enable
the gate before that approval.

## Stage13-F2L — VEMA-246 read-only target preflight

Teddy selected `VEMA-246` as a canary candidate. This selection is not
authorization to permanently delete it. This checkpoint performed no prepare
or validate HTTP request because no safe authenticated browser session was
available for reuse (`AUTHENTICATED_PREPARE=NOT_REPLAYED`). No token was issued.

Git preflight was clean at source HEAD
`c06f83ab2af2fa9495663fc9f4e93bbb8cce2ca1`, branch
`teddy-subtitle-stage11`, equal to the exact remote branch head. Production web
was running the F2F image
`sha256:bac75af6716cd7a0e33aa671b90f9386926d8dc93f64dba201caa6494283e404`
with restart count 0. `TEDDY_LIBRARY_DELETE_ENABLED=false`, title-lock config
was `/run/teddy-title-locks`, and the Discovery writer health operation
returned READY. Completion runtime marker remained
`705bf9e700156d88523babfad15861a5faee9ff2`; completion timer and service and
the reconcile-apply service were inactive. The reconcile-apply path remains a
manual one-shot with no automatic apply timer; F2K's short global-lock
contention evidence keeps `CANARY_RECONCILE_FREEZE_READY=YES`.

The Discovery DB was opened `mode=ro` with `PRAGMA query_only=ON`. Exactly one
present JAV holding matched: holding_id=20, DVD-ID `VEMA-246`,
`VEMA/VEMA-246/VEMA-246.mp4`, `MATCHED`, size 2,844,299,563 bytes,
mtime_ns=1788054184863651608, discovered_by `library-inventory`. The deployed
canonical mapping agreed on family `VEMA`, directory `VEMA/VEMA-246`, media
filename `VEMA-246.mp4`, and extension `.mp4`.

The exact title directory was inspected over the hardened NAS SSH transport
using lstat on root/family/title and direct entries only. All four entries
were regular files; there were no symlinks, nested directories, special files,
unsafe names, or path normalization/containment failures. Canonical manifest
identity SHA-256 (metadata identity, not content hash) was
`121aefa01eb2d6cd9ae6b99695892cf4652aa4b33d50e65a4c3208b6ef3c8677`, with
4 files totaling 2,844,317,586 bytes. The canonical media size and mtime_ns
matched the holding. Filenames: `VEMA-246.ko.srt` (KO subtitle),
`VEMA-246.mp4` (video), `movie.nfo`, and `poster.webp`; no JA/EN subtitle was
present. Subtitle file contents were not read or output. No absolute NAS path
was included in the manifest report.

Target state was read by exact DVD-ID. The latest organizer job (job_id=56)
was `COMPLETED`; the Stage12 rollout row was `PUBLISHED`, which is terminal
under the current status contract (active states are RUNNING/GENERATED). The
heartbeat was stale `COMPLETE` with no current DVD-ID. No media job row
existed, so `TARGET_MEDIA_JOB=NONE`. The production activity guard returned
IDLE. `TARGET_MEDIA_READY=YES`.

The production Jellyfin reconciler's bounded read-only GET path returned
exactly one item matching `/media/adult/VEMA/VEMA-246/VEMA-246.mp4`.
No Jellyfin mutation was called. The host writer's `preflight_holding`
returned READY; this is the writer's BEGIN IMMEDIATE / exact validation /
ROLLBACK preflight. The target title lock returned ACQUIRED on both host and
web container and was immediately released. Host and container observed the
same lock-file device/inode (1796:548375); the file was regular, mode 0600.

Before/after read-only snapshots were unchanged: VEMA-246 remained present=1
with the same holding identity; current present JAV holdings remained 184,
unique DVD-ID count 184, duplicate count 0, and canonical/parse mismatch count
0. No conflicting completion/reconcile/Stage12/subtitle process was observed.
Completion timer remained inactive (enabled, not started); reconcile-apply
remained inactive; delete gate remained false. The production web app received
no prepare, validate, commit, resume, or reconcile request. Discovery content,
media state, durable provenance, NAS, and Jellyfin were not mutated; actual
delete=0.

`TARGET_CANARY_READY=YES`, subject to a separate final irreversible approval.
This means only that the read-only preflight passed. It does not authorize
enabling the feature gate, performing a fresh prepare/validate, or deleting
VEMA-246. Next: present this evidence to Teddy and obtain explicit final
confirmation for VEMA-246 immediately before a separate actual-delete
checkpoint. Until then, keep the gate false and do not prepare, validate, or
commit.
