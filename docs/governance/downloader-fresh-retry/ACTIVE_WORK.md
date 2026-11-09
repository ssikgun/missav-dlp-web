# Downloader explicit fresh-identity HLS retry API — active work

WORKSTREAM: downloader-fresh-retry
TASK_ID: DLFR-001
STATUS: IN_PROGRESS
CONTRACT_VERSION: 1.0.0
REQUIRES_WORKSTREAMS: downloader-fresh-retry

## OBJECTIVE

Provide one safe explicit API for a failed custom-HLS download to begin a **new-identity** download without modifying its preserved failed record and segments. Initial intended consumer: the separately gated DLHLS-001 SORA-489 trial.

## APPROVED_SCOPE

- Teddy explicitly replied `승인해` on 2026-11-09 to registering an independent API-only task and preparing a minimal implementation; prior remediation/prevention code and conditional operating application were already approved in principle.
- Implement the smallest authenticated + CSRF-gated `POST /api/tasks/<failed_id>/retry-fresh` route (exact path may match existing route conventions), preserving normal `/download` duplicate behavior, existing old-ID retry and current job/queue locks.
- Create a unique new task with the existing original URL and its justified route, isolated parts directory and **new-record-only** provenance. Fail closed for nonfailed/non-HLS records, active collisions, held/missing owners, NAS or local output collision, insufficient reserve or uncertain state; do not alter originals.
- Perform proportional offline tests using actual existing safety/admission helpers and read-only runtime baselines. Prepare a code-only candidate image based on the verified operating image when possible; preserve live UI file SHA baseline exactly and avoid merging held P08LIB UI source.
- After an independently verified CT108 A-method build/rollback/preflight, conditionally allow one `missav-dlp-web`-only API release; record BUILD, DEPLOY, runtime health and UI-parity separately. Do **not** enqueue incident jobs under this task.

## PROHIBITED_SCOPE

- No modifications to the original 3 failed tasks, 1,395 TS, saved HLS manifests, playlist identity, existing MP4/NFO/posters, existing job states, storage reserve or globally single MP4 worker.
- No UI HTML/JS/CSS, ordinary `/download` and `retry` behavior change, generic duplicate guard removal, import-time production side effects, alternate URL spoofing, title-specific hack or extra automatic downloads.
- No P08LIB-001 UI promotion, Writer, Stage9, Stage11, NAS/Jellyfin writes, broad Compose replacement, Docker prune, dirty checkout overwrite or new upstream network probes.

## ACCEPTANCE_CRITERIA

- Fresh separate `downloader-fresh-retry / DLFR-001 / IN_PROGRESS` route, this v1.0.0 approved contract, and self-only active work pass structural and DLFR task-specific governance checks; unrelated workstream IDs remain unchanged.
- Representative tests prove explicit new UUID and new job/parts isolation while preserving original error/task content and TS; normal duplicate guard still blocks ordinary same-title enqueue; error/ownership/space/concurrency failures refuse any new job; auth/CSRF and original HLS semantic-plan protections remain enforced.
- Candidate image contains only approved API/runtime Python delta, no held UI change, and has a verified rollback route; production stop/build/promotion proceed only on separate CT108 safety gates and are not implied by registration or offline PASS.
- Actual recovery attempts remain a separate DLHLS-001 operator GO. SORA-489 current source title/required size and real worker status need fresh clearance; original three jobs remain untouched until that separately gated trial.

## EVIDENCE

- Previous verified live CT108 output: all 3 original failed records, TS 1323+72+0=1395, SORA-489 network route VPN and saved display title, free 36.53 GiB / reserve 4.89 GiB, no busy task records or MP4 queue JSON, but no live process/thread proof.
- Saved-title candidate MP4/TS absent locally and on remote SSH NAS; ownership DB returned SORA-489 unowned. The present `teddy_duplicates.guarded_enqueue` treats error jobs as nonterminal and blocks normal new entry with 409, whereas old retry reuses the protected task ID and mismatched HLS plan.
- User approval covers registration and preparing the minimal API implementation; this registration is documentation-only. `CODE=NOT_RUN`, `BUILD=NOT_RUN`, `DEPLOY=NOT_RUN`, `DOWNLOAD=NOT_RUN`.

## NEXT_DECISION

Run governance structural and DLFR task-specific preflight in a verified clean canonical checkout; design and implement the isolated authenticated fresh-ID action with representative tests. Before any build or deployment, verify live CT108 idle/space+reserve, A-method stop and confirmed build completion, Compose rollback and exact UI SHA parity. Request the independent DLHLS-001 live-trial GO only after operational source/output/capacity checks.
