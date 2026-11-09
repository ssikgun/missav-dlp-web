# Downloader explicit fresh-identity HLS retry API — active work

## 2026-11-09 13:21:39 KST — DLFR-001 atomic new-record wrapper fixtures PASS; full API still BLOCKED

- **Codex report against canonical `10ce37019d9eeaf72e069b7ba6313806c84a79db`:** `ROUTING=PASS` (two governance checks). Only a new-task safe-save/queue wrapper was added to isolated `/tmp/dlfr-001-candidate`; the `POST /api/tasks/<failed_id>/retry-fresh` endpoint is **not connected** and `CODE=BLOCKED`.
- **Scope of PASS:** bounded fixtures for successful new-job admission, state-save failure, queue insertion failure and partial queue insertion failure proved recovery of preexisting in-memory and on-disk task maps and queue within that isolated fixture. This is **not** an end-to-end API PASS or live crash/restart proof. `NEW_TASK_ATOMICITY=BLOCKED` until full route integration.
- **Not run / not verified:** authenticated CSRF action, two concurrent requests for the same failed source, normal `/download` duplicate behavior, dynamic actual-output filename collisions locally and via SSH NAS, full live original-state audit and TS count. Prior CT108 1,395 TS observation remains historical; do not claim it was recounted by this run. `UI_ISOLATION=PASS` for no UI source changes; `BUILD/DEPLOY/DOWNLOAD=NOT_RUN`.
- **Candidate provenance:** isolated partial patch `/tmp/dlfr-001-partial-atomic.patch`, SHA-256 `a69ff26b872a9883d2d56a70e5bfb58e22769e771a44ee182f422db38841b18f`. No product-code GitHub commit or CT108 changes. The local candidate is **not deployable**.
- **Next bounded approved step:** Reuse the already-tested new-record transaction in the existing protected admin/API route; add a single authenticated + CSRF explicit fresh-ID HLS action, per-parent concurrency and active-child/ownership/reserve gates, and current extracted-filename local/NAS no-overwrite check before any media output. Run one representative integrated success case plus auth, CSRF, concurrency, duplicate, collision and a rollback regression; preserve original job and 1,395 TS. If a guard requires unapproved generic runtime changes, stop and report the specific contract conflict. No build, promotion, source probe, original-ID retry or network download.

## 2026-11-09 12:19:34 KST — DLFR-001 first Codex CODE BLOCKED; new-record transaction missing

- **Teddy's Codex result on canonical `602534deb2f759a25f0f75763a0d34658e5f9fd9`:** `ROUTING=PASS` (two governance checks), `CODE=BLOCKED`; `OFFLINE_TEST/AUTH_CSRF/DUPLICATE_GUARD/ORIGINAL_DATA_PROTECTION/UI_ISOLATION=NOT_RUN`; `BUILD/DEPLOY/DOWNLOAD=NOT_RUN`; no new product code or GitHub commit. Candidate exists only as unproven isolated `/tmp/dlfr-001-candidate`. Prior actual CT108 count of 1,395 TS remains the last verified evidence; this Codex run did not recount them.
- **Verified canonical implementation gap:** `teddy_routing.enqueue_download` creates a new UUID then calls `core.save_tasks()` separately from `core.download_queue.put()`; on a queue failure this is not a proven all-or-nothing new-record admission. `downloader_runtime_overlay/app.py:persist_retry_state_and_enqueue` includes verified on-disk backup/rollback and `_retry_queue_put` rollback for an **existing** task transition, but failure rollback mutates the existing task mapping and does **not** prove deletion of a newly inserted key. Do not reuse it unchanged for the new API or infer crash-safe new-record semantics from retry tests.
- **Next minimal authorized code step:** Implement a specific new-UUID create+durable-state+queue transaction that reuses the existing file-safe staging/restore and checked queue insertion, but on failure restores the **exact old task mapping and disk snapshot**, including removing a newly inserted key. Check that failed save, failed queue, and concurrent same-parent requests leave no orphan task, queued item, original mutation or duplicate fresh child. Preserve existing `/download` and same-ID retry behavior, existing ownership/auth/CSRF/capacity checks, prior HLS plan guard and P08 UI HOLD. The current dynamically re-extracted title means saved-title NAS/local absence is evidence only; exact current output must remain guarded when metadata becomes known before media writing and publication.
- **Operational status:** No real API call, code promotion, Docker image build, deployment, network trial or download GO. `DLFR-001 / IN_PROGRESS` approved contract unchanged. Next code run should produce an offline candidate and real tests, not consume a live trial or touch CT108.

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
