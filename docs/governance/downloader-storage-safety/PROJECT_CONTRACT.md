# Downloader build/download shared-storage safety contract

CONTRACT_VERSION: 1.0.1
PROJECT_CONTRACT_STATUS: APPROVED
APPLIES_TO: Only Docker image build versus Downloader download/MP4-remux shared-filesystem contention prevention, now using Teddy-approved Downloader-only maintenance stop for each build and explicit verified restart (2026-11-09).

## Purpose and precedence

- Prevent a Docker image build on the same filesystem from overlapping Downloader download/remux work by confirming a quiescent state and temporarily stopping only `missav-dlp-web` throughout the build; keep required disk/reserve headroom and fail closed before an explicit restart.
- This narrow independent workstream `downloader-storage-safety` owns only the build-vs-download contention maintenance gate and its CT108 preflight/rollback procedure. It takes precedence over generic `downloader / P08LIB-001` routing solely for this gate; it does not authorize ordinary Downloader UI, queue or media changes.
- Ordinary download behavior, general queue/concurrency changes, other source changes, UI/API, Stage9, Discovery Writer, Stage11, subtitles, NAS/Jellyfin publishing and the three original DLHLS-001 incident jobs retain their existing separate routes. If a proposed change materially changes one of those, stop for a separately aligned workstream task, not an implicit expansion.
- Keep existing `P08LIB-001` four-way UI approval and operational HOLD, `DLHLS-001` independent incident task and `S11-WX011` unchanged.

## Existing mechanisms and approved maintenance design (A — 2026-11-09)

- Teddy explicitly chose **A: stop only Downloader for each infrequent Docker image build**. The previous mandatory always-on cooperative build/download file-lock design is superseded for this narrow purpose. Do not ship the incomplete `/tmp/dlss-001-candidate` lock/marker experiment merely to satisfy the former design; preserve it as historical candidate evidence.
- Reuse canonical `downloader_runtime_overlay/teddy_download_safety.py` existing capacity/reserve/lease checks and globally serialized MP4 remux policy where applicable; no duplicate framework, new title exception, queue behavior change, or reduced reserve.
- Before build: verify the exact current service/image/Compose identity, no active/queued/retrying download or MP4 work (including process/thread state), and disk headroom for Docker layers, build temp output and safety reserve on the *actual shared filesystem*. A task-status snapshot alone is insufficient. Fail closed on uncertainty.
- Stop **only** the `missav-dlp-web` container after the zero-work check and verified restore/rollback plan. Confirm it remains stopped before and throughout the image build; do not change or stop Gluetun, Selkies, Writer, Stage9 or other services. The `unless-stopped` policy is supporting evidence, not a substitute for observing the container state.
- If the build CLI exits early, fails, or Docker daemon-side activity may continue, **keep Downloader stopped**; independently verify build completion and disk safety before any manual restart or candidate promotion. Never auto-release a marker, auto-restart or claim build completion from wrapper exit alone. A direct unmanaged `docker build` may bypass the prescribed maintenance procedure; document this operating limitation.
- Preserve existing clear hold/retry reasoning, existing download concurrency and globally single MP4 remux. Protect existing jobs, outputs and no-overwrite boundaries. Representative offline/read-only checks should validate stop-state/rollback/fail-closed behavior without doing a test production build.
- Preserve existing tasks, .parts, all 1,395 last-verified TS fragments, resume plans, manifests, completed MP4/NFO/posters, backups, Docker images and rollback; no deletion, cleanup, pruning, overwriting or changed HLS plan SHA bypass.
- Avoid broad infrastructure refactors; use representative offline tests for mutual exclusion and storage shortage, followed by small bounded production-read-only checks.

## Authorized implementation and operational scope

- Teddy approved the distinct `DLSS-001` registration on 2026-11-09 after previously approving code change and conditional operational application to fix and prevent the shared-storage conflict.
- Permitted: smallest Downloader-only maintenance preflight/stop/build/verified-manual-start runbook (or equally bounded helper), scoped read-only and offline tests, isolated exact-source/image candidate, at most one conditionally authorized Docker image build and one `missav-dlp-web`-only targeted promotion if every live gate passes and the image includes **no held/unapproved P08LIB-001 UI delta**. The incomplete automatic admission lock and marker release candidate is not required or approved for deployment.
- Production cutover requires current exact live image/source manifest, authentic CT108 Docker/Compose access, verified no active/queued/retry downloads/remux or other builds, measured peak build+reserve headroom, safe service-only stop, unchanged held UI, and validated Compose/rollback snapshots plus explicit go/no-go. If any check fails, do not start build; after a completed stop, retain the stopped state for informed recovery if build completion/identity is uncertain. Do not guess identity or bypass a block.
- Do not mutate the DLHLS-001 three old jobs or start/retry downloads under this workstream. Any bounded incident recovery trial must comply independently with DLHLS-001 source/output/collision/capacity gates; completing DLSS-001 does not imply a recovery job is safe.

## Acceptance criteria

- The router has `downloader-storage-safety / DLSS-001 / IN_PROGRESS`, this contract v1.0.1 APPROVED and self-only active work; governance structural and explicit DLSS task preflight PASS while unrelated selected workstreams still reject the DLSS task ID.
- A CT108 Downloader-only maintenance stop reliably prevents any download/remux from overlapping the image build, with current worker/queue, capacity/reserve and Docker build-completion/rollback gates demonstrated before manually resuming; representative fail-closed tests and explicit unmanaged-Docker bypass limitation are recorded. No unproven automatic build-lock or marker code is deployed.
- Real deployment is reported separately from code/test/build evidence, preserving existing system state and unrelated workstreams. UI promotion remains HOLD unless independently authorized through its existing four-way task.

## Fail-closed conditions

- No generic queue, HLS semantic-plan, Stage9/Writer/Stage11 or UI changes without independently aligned approval. No automatic service restart or redeploy, cleanup, prune, retry of failed jobs or NAS/Jellyfin writes. Never resume Downloader while Docker build completion is unknown.
- If the clean build would incorporate the held `P08LIB-001` UI change, do not promote that image through DLSS-001; prepare a separated candidate or report a concrete block.
