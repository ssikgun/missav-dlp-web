# Downloader shared-storage admission safety — active work

## 2026-11-09 — DLSS-001 authentic CT108 read-only baseline (NO DEPLOYMENT)

- **Teddy's real `root@downloader` read-only command output:** `READ_ONLY_INSPECTION=PASS`, `DEPLOYMENT_GATE=NOT_ASSESSED`. Live `missav-dlp-web` container `2a72fddff02b5ca2c86da5d44dc3bd6b5a2157a782b65685cb3121092bde33fd`, image `sha256:ebd164d631450660b79ca29141a3b8c317f71df443b2d209feec51a8a35c000a`, restart policy `unless-stopped`. The live container's Compose label lists 13 layered input files, ending with P08LIB CSS and DB-UI candidate overrides; labels alone **do not prove** which held UI contents were promoted. Existing service/other container identities and effective Compose rollback were not yet verified.
- **Shared volume/capacity:** Host `/opt/missav-dlp-web/work` and the actual Docker root returned by `docker info` both map to `/dev/loop4`, ext4, mounted on `/`. `df -B1` reports 105089568768 total bytes, 60863143936 used, **39227527168 available bytes** (~36.53 GiB). This confirms shared filesystem but not image-build peak usage + outstanding reservations + safety reserve headroom. No shared flock inode or build-lock admission test was performed.
- **Task/process snapshot:** `TASK_STATES={'완료': 10, '에러: 저장 공간/잠금 보호: HLS 세그먼트 계획이 기존 재개 자료와 달라 조각을 보존했습니다.': 3}`; `MP4_QUEUE_RECORDS=0`; `docker top` listed one `python` process. The three statuses are complete error-message strings, **not** literal `status='에러'`; do not use an exact-'에러' preflight assertion. These observations alone cannot rule out application threads, delayed retry/admission, host builds, or other future work. Live 1,395 TS count and contents were not rechecked; three old HLS tasks remain protected.
- **Exact current live UI baseline SHA256:** `/app/templates/index.html=84609dc23a2c3583bd099a6a2f0ed7e2301bb7645321e087b73595cb88326563`; `teddy-library.css=e6c2f92d8f45b0d08287a7e7b05f202d48a47e4470a349da74d782a015efe131`; `teddy-library.js=c4343f99fb80674d4d26bb42545364b72a348c32adf7c4667fa26146cefb5963`; `teddy-subtitle-status.css=60d0df99ca59b9cd699d1db1a118f4b986e1b32d9ec70ee6ab44d3499a90d095`. An approved DLSS-only image candidate must preserve these actual baseline files or obtain separate P08LIB approval; compare exact runtime image contents, not merely source branch paths.
- **Next gate:** Keep `CODE/LOCK_TEST/FIRST_CUTOVER/UI_ISOLATION/ROLLBACK_READY=BLOCKED`, `BUILD/DEPLOY=NOT_RUN`. Complete the host guarded-build entrypoint and cooperating full-duration downloader+MP4 locks in the isolated candidate; verify no-new-admission maintenance bridge for old-image first cutover, correct current task/error-state handling, peak disk+reserve, 13-file Compose/effective rollback, and exact UI manifest before any build. Preserve existing media, three failed jobs/TS, backups/images and unrelated services. Stop on any unverified condition; no automatic retries, prune, forced restart or held UI promotion.

## 2026-11-09 10:02:12 KST — DLSS-001 follow-up candidate remains BLOCKED (NO BUILD/DEPLOY)

- **Teddy-supplied Codex result on canonical `dad13947eb2613c4ea1884dc2b565cee21588de9`:** `ROUTING=PASS` (both governance checks); `CODE=BLOCKED`, `LOCK_TEST=BLOCKED`, `FIRST_CUTOVER_GATE=BLOCKED`, `UI_ISOLATION=BLOCKED`, `BUILD=NOT_RUN`, `DEPLOY=NOT_RUN`, `DATA_PROTECTION=BLOCKED`, `ROLLBACK_READY=BLOCKED`. No new GitHub commit. A candidate under `/tmp/dlss-001-candidate` reportedly received partial download/MP4 shared-lock changes, but the exact candidate diff was not independently inspected in this ChatGPT session.
- **Bounded evidence and remaining gaps:** Isolated process-contention, process-exit lock release and insufficient-space representative tests passed. They do **not** prove same-inode coordination on actual CT108 mount or all runtime paths. Host guarded Docker-build entrypoint and reservation/queued-task accounting remain disconnected; raw `docker build` bypass remains. Live download/remux/build state, first-cutover stop/restart safety, exact current image-derived candidate UI hashes and real Compose rollback are unverified. Existing jobs reportedly untouched, but current inventory of previously verified 1,395 TS fragments was not rechecked; isolated handoff drafts were not pushed.
- **Immediate safe next checkpoint:** Keep the candidate `NOT DEPLOYABLE`. First collect a bounded, authenticated, **read-only CT108** evidence set for active/queued/automatic-retry jobs, running MP4 worker/builds, actual mount/lock-inode identity, current image/Compose and rollback path, storage+reserve/peak build headroom and held UI content baseline. Independently complete the host build entrypoint and full-life cooperating download/remux lock in isolation, then compare the resulting runtime-image-derived DLSS-only candidate with the exact live UI manifest. Re-run one representative full-path contention test. On any mismatch or missing access report `BLOCKED`; do not build, deploy, retry old jobs, prune images, remove TS or promote `P08LIB-001`. Checkpoint verified facts separately from reported test results.

## 2026-11-09 — DLSS-001 09:39 partial-lock follow-up (NOT DEPLOYABLE)

- **Source of this checkpoint:** Teddy's continuation of the 09:39 KST Codex result (summary only; exact candidate diff, tests and CT108 state were not independently available in this ChatGPT session). Some lock implementation was reportedly written, but there is still **no proven end-to-end connection** in which the host Docker build, Downloader new-download admission and separate MP4 worker share the same effective lock. Do not treat partial source edits as an installed safeguard.
- **Effective status:** `CODE=PARTIAL_REPORTED_NOT_VERIFIED`, `CROSS_PROCESS_GATE=NOT_PROVEN`, `TEST=CONFIRM_NEEDED`, `BUILD=NOT_RUN`, `DEPLOY=NOT_RUN`; current live runtime is not known to honor a new lock. The held `P08LIB-001` UI must not be bundled into a DLSS-001 image. CT108 worker state, peak build/remux/download plus reserve capacity, exact running image and rollback remain `CONFIRM_NEEDED`. Preserve the three failed HLS jobs, last-verified 1,395 TS fragments, tasks, existing images and backups; no retry, deletion, pruning or UI promotion.
- **Next focused Codex step:** Verify the real Dockerfile's final runtime overlay and both `downloader_runtime_overlay/teddy_bootstrap.py` / `teddy_mp4_queue.py` worker admission against the host guarded build path. Prove first-cutover safety using a bounded Downloader-only no-new-admission maintenance hold with zero active download/remux before any build; do not assume the old image participates. Separately prove an exact-live-image-derived DLSS-only candidate excluding held UI files, offline mutual-exclusion and reserve tests, and authentic CT108 no-active-work/capacity/Compose/rollback gates. Stop and report `BLOCKED` on any failed/unknown condition; only then use the already-approved single conditional build and targeted Downloader-only deployment. Document manual raw Docker-build bypass and checkpoint results immediately.

## 2026-11-09 — DLSS-001 Codex first-cutover and UI-isolation blockers (NO IMPLEMENTATION)

- **Codex reported at 2026-11-09 09:23:01 KST:** `ROUTING=PASS` (both governance structural/selected checks); `CODE=BLOCKED`, `TEST=NOT_RUN`, `BUILD=NOT_RUN`, `DEPLOY=NOT_RUN`, `RECOVERY=BLOCKED`, `DATA_PROTECTION=CONFIRM_NEEDED`. Isolated candidate worktree `/tmp/dlss-001-candidate`; no changed files or new GitHub commit. Existing three failed jobs and TS were not edited, but live 1,395 TS count was **not reverified in this Codex run**. Current P08 UI rollout remains HOLD.
- **Concrete blockers:** Before first installation, currently running old downloader image does not cooperate with a proposed new shared Docker-build/download lock, so the first guarded build could still race a new download. The latest canonical whole-source Dockerfile build would also bundle held `P08LIB-001` UI CSS changes, violating DLSS-001 isolation. Authentic CT108 process state, available peak build+download/remux+reserve headroom, and rollback/Compose details were not verified in that Codex session.
- **Proposed safe implementation route (NOT YET VERIFIED/EXECUTED):** Solve first-cutover by a bounded **Downloader-only maintenance/admission hold** before any image build, with a zero-active-task + remux/process check, no unrelated Compose service change and a verified restoration/rollback plan; this replaces any false assumption that the old image participates in the new lock. For source isolation, investigate a clean **runtime-image-derived overlay candidate** based on the exact current live Downloader image and only the DLSS-001 guard files, with reproducible source/target checks and tests; do not rebuild/promote the broad GitHub source with held UI changes or copy unpatched build-time sources over the deployed patched runtime. The future guard must coordinate cooperating host build and container download/remux through the **same lock inode**, with an explicit raw manual Docker-build bypass limitation. Whether these approaches satisfy real CT108 permissions, dependency impact, source manifest and memory/disk safety is `CONFIRM_NEEDED`.
- **Immediate next:** In one focused Codex pass, prove or reject the two proposed bridge gates from actual running Docker image/Compose and targeted source, implement and offline-test the minimum safe candidate in isolation if possible, and execute a single conditional build/deployment **only** after actual no-active-work, hold, filesystem+reserve, UI-delta and rollback checks. Do not ask for another broad user approval already given; no old-job retry, new HLS probe, image prune or unauthorized UI release. Record implementation/rollout separately as PASS/BLOCKED/NOT_RUN.


## 2026-11-09 — DLSS-001 independent workstream registered and implementation authorized

- **Teddy approval:** After receiving `ROUTING=BLOCKED, CODE=NOT_RUN, TEST=NOT_RUN, BUILD=NOT_RUN, DEPLOY=NOT_RUN, RECOVERY=BLOCKED` from Codex, Teddy explicitly replied `응 승인해` to the proposal to register `downloader-storage-safety / DLSS-001`, without replacing `P08LIB-001` or `DLHLS-001`. Earlier on 2026-11-09 Teddy also stated `코드 변경, 운영 적용까지 모두 승인할께`, conditional on product/operational safety.
- **Independent ownership:** Cross-boundary Docker-build versus downloader shared-disk exclusion/space headroom only. Generic download functional changes and three-job recovery remain outside this task. Preserve existing UI HOLD, Writer, Stage9, Stage11, NAS, Jellyfin and old failed jobs; no new network/source-page probes.
- **Verified starting evidence:** On CT108 `/opt/missav-dlp-web/work` and `/var/lib/docker` were both on `/dev/loop4`, `FREE_GIB=36.54`, and task JSON showed 0 active/0 queued; initial 2026-11-07 HLS stoppages had storage safety `free < required + reserve`, but actual Docker build causal contribution is NOT_PROVEN. Existing `downloader_runtime_overlay/teddy_download_safety.py` has `reserve_bytes`, `ensure_space`, `StorageReservation`, `StorageWriteTransaction` and global serial remux; reuse instead of replacing.
- **Registration action:** Add this self-only route, approved v1.0.0 contract and this `DLSS-001` active task. Do not change existing workstream task IDs, contract versions or common validator; read back exact remote head after fast-forward. Registration alone has no product/operational side effect.

WORKSTREAM: downloader-storage-safety
TASK_ID: DLSS-001
STATUS: IN_PROGRESS
CONTRACT_VERSION: 1.0.0
REQUIRES_WORKSTREAMS: downloader-storage-safety

## OBJECTIVE

Prevent Downloader storage-guard failures from overlapping Docker builds and downloads/remux on the same CT108 filesystem, without weakening the existing safety reserve or altering unrelated services.

## APPROVED_SCOPE

- Inspect only relevant existing code and runtime capacity/reservation/build path; implement minimum cooperating build/download admission exclusion and required+reserve+build headroom checks.
- Reuse the existing storage reservation and process locking where possible; keep downloads concurrency policy and globally single MP4 remux unchanged.
- Implement an actual guarded Docker build path that cannot silently run simultaneously with normal Downloader download/remux admission; document any raw manual Docker bypass rather than claiming universal exclusion.
- Build/run proportionate representative tests in an isolated clean checkout; one conditionally permitted build and targeted `missav-dlp-web`-only promotion if all live safety/image-delta/rollback gates PASS.
- Record meaningful checkpoints immediately in this ACTIVE_WORK and the single existing canonical `CURRENT_HANDOFF.md`.

## PROHIBITED_SCOPE

- No recreation/removal of protected failed HLS tasks, TS, resume plans, jobs, backups or existing images; no ordinary retry, playlist-SHA override, storage reserve reduction, queue-wide overhaul or new downloads.
- No generic Downloader behavior changes outside the shared-storage admission boundary; no P08LIB-001 UI promotion, held CSS inclusion in production, Stage9, Writer, Stage11, other Compose services, NAS/Jellyfin/DB write or Docker image/cache prune.
- No modifying a protected dirty worktree, undeclared network retry, automatic second build, silent rollback, forced Git push or ad-hoc Docker promotion.

## ACCEPTANCE_CRITERIA

- Exact self-only DLSS-001 route + approved contract + active task pass structural governance and task-specific checks; prior workstreams and their task IDs remain unchanged.
- Admission overlap and no-reserve-space cases fail closed in representative tests without affecting actual downloads or remux concurrency.
- One build and one service-only promotion only if clean image contents, current CT108 capacity+reserve, worker/process state, rollback and no held UI source changes are verified; separate BUILD/DEPLOY/PRODUCT PASS, BLOCKED or NOT_RUN.
- No preexisting 1,395 TS fragments or task/NAS/Jellyfin user data modified; existing `DLHLS-001` incident recovery independently gated.

## EVIDENCE

- Teddy explicitly approved storage-prevention code changes and conditional operating application on 2026-11-09 and then separately approved this new DLSS-001 workstream registration.
- Last-read CT108 source and disk facts show a shared filesystem, existing reserve/lease guards, and failed HLS jobs protected by storage and plan-SHA guards; no deployment or recovery has been executed under this task.

## NEXT_DECISION

Validate newly registered route with `python3 scripts/check_project_governance.py --all-workstreams` and `python3 scripts/check_project_governance.py --workstream downloader-storage-safety --task-id DLSS-001` in a verified clean source checkout. Then implement minimal admission/build guard, test, and conditionally deploy only if the live source, UI-delta, disk headroom and rollback gates are all PASS; otherwise report BLOCKED without retry or source-page probes.
