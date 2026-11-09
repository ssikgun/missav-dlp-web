# Downloader shared-storage admission safety — active work

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
