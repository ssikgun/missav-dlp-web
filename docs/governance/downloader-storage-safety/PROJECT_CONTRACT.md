# Downloader build/download shared-storage safety contract

CONTRACT_VERSION: 1.0.0
PROJECT_CONTRACT_STATUS: APPROVED
APPLIES_TO: Only the cross-process Docker image build versus Downloader download/MP4-remux shared-disk admission and resource guard, approved by Teddy for code change and conditional operational application on 2026-11-09.

## Purpose and precedence

- Prevent a Docker image build on the same filesystem from starting or proceeding without accounting for ongoing Downloader download/remux reserved space and safety reserve; prevent new download admission from racing an authorized guarded build.
- This narrow independent workstream `downloader-storage-safety` owns only the cross-boundary contention/admission mechanism and the associated CT108 build gate. It takes precedence over the generic `downloader / P08LIB-001` routing solely for this mechanism, even where a guard implementation lives in a generic downloader source file.
- Ordinary download behavior, general queue/concurrency changes, other source changes, UI/API, Stage9, Discovery Writer, Stage11, subtitles, NAS/Jellyfin publishing and the three original DLHLS-001 incident jobs retain their existing separate routes. If a proposed change materially changes one of those, stop for a separately aligned workstream task, not an implicit expansion.
- Keep existing `P08LIB-001` four-way UI approval and operational HOLD, `DLHLS-001` independent incident task and `S11-WX011` unchanged.

## Existing mechanisms and required design

- Reuse the canonical `downloader_runtime_overlay/teddy_download_safety.py` storage reserve/lease/check functions and globally serialized MP4 remux policy where applicable; no duplicated parallel safety framework or title-specific exceptions.
- Consider Docker image layers, temporary build output, download reservation, remux output headroom and current free space on the *actual same filesystem*. An approved build must not silently bypass the admission/lock protection used in normal operation. Explicitly state if unmanaged `docker build` commands can bypass it.
- Fail closed under ambiguous/shared filesystem identity, missing reservation state, unsafe lock path, incomplete worker state, insufficient required+reserve+build headroom, or attempted output collision. Preserve user-visible, clear hold/retry reasoning. Never change currently configured download concurrency or MP4 global one-at-a-time remux rule.
- Preserve existing tasks, .parts, all 1,395 last-verified TS fragments, resume plans, manifests, completed MP4/NFO/posters, backups, Docker images and rollback; no deletion, cleanup, pruning, overwriting or changed HLS plan SHA bypass.
- Avoid broad infrastructure refactors; use representative offline tests for mutual exclusion and storage shortage, followed by small bounded production-read-only checks.

## Authorized implementation and operational scope

- Teddy approved the distinct `DLSS-001` registration on 2026-11-09 after previously approving code change and conditional operational application to fix and prevent the shared-storage conflict.
- Permitted: smallest generic storage-admission guard and a cooperating host Docker-build entrypoint / preflight, scoped tests, isolated clean-source build context and at most one conditionally authorized Docker image build, then a `missav-dlp-web`-only targeted deploy if every live gate passes and the image includes **no held/unapproved P08LIB-001 UI delta**.
- Production cutover requires current exact source SHA and manifest, authentic CT108 Docker/Compose access, no running downloads/remux/builds, measured capacity with peak build+download/remux+reserve headroom, clear staging/rollback snapshots and explicit go/no-go. If any check fails, stop with no partial deploy. Do not guess source or output identity, or bypass a block.
- Do not mutate the DLHLS-001 three old jobs or start/retry downloads under this workstream. Any bounded incident recovery trial must comply independently with DLHLS-001 source/output/collision/capacity gates; completing DLSS-001 does not imply a recovery job is safe.

## Acceptance criteria

- The router has `downloader-storage-safety / DLSS-001 / IN_PROGRESS`, this contract v1.0.0 APPROVED and self-only active work; the governance structural check and explicit task preflight PASS while unrelated selected workstreams still reject the DLSS task ID.
- Mutually exclusive *cooperating* build/download admission and correct reserve checks are demonstrably effective for the real mounted filesystem and a bounded representative test. State precisely any manual-Docker bypass limitation.
- Real deployment is reported separately from code/test/build evidence, preserving existing system state and unrelated workstreams. UI promotion remains HOLD unless independently authorized through its existing four-way task.

## Fail-closed conditions

- No generic queue, HLS semantic-plan, Stage9/Writer/Stage11 or UI changes without an independently aligned approval. No automatic redeploy, cleanup, prune, retry of failed jobs or NAS/Jellyfin writes.
- If the clean build would incorporate the held `P08LIB-001` UI change, do not promote that image through DLSS-001; prepare a separated candidate or report a concrete block.
