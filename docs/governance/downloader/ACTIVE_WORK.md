# Downloader non-subtitle workstream — active work

WORKSTREAM: downloader
TASK_ID: DL-001
STATUS: IN_PROGRESS
CONTRACT_VERSION: 1.0.0
REQUIRES_WORKSTREAMS: downloader

## OBJECTIVE

Stabilize download and MP4 processing concurrency, safe behavior under storage pressure, and preservation of recoverable download fragments. This shared registration phase must complete and be read back from the canonical remote before any product-code work begins.

## APPROVED_SCOPE

- Inspect the existing download and storage code and actual Docker build/runtime patch path.
- Verify configured download concurrency and implement globally serialized MP4 conversion, independently of download worker count.
- Add safe wait/stop behavior for insufficient storage, distinguish ENOSPC, prevent unnecessary TS fallback, and prevent duplicate or repeated automatic retries.
- Preserve HLS `.parts`, TS segments, filelists, task state, and existing final files until final storage is verified.
- Analyze code-level reuse/recovery paths for the four existing failed jobs; use synthetic fixtures for offline remux/recovery tests only.
- Add offline tests and verify the final Docker build patch path in an isolated worktree; prepare a reviewable implementation candidate.

## PROHIBITED_SCOPE

- Do not restart or deploy production containers; run or retry real downloads; or perform real MP4 recovery on the four failed jobs.
- Do not modify operational `.tasks.json` or `.settings.json`, real `.parts`/TS/MP4 files, NAS/Jellyfin data, or Proxmox settings.
- Do not move or delete operational data, write to NAS, or perform production cleanup.
- Do not modify Stage11 contracts, state, code, model environments, or artifacts.
- Do not treat this task as authorization for production deployment or operational recovery.

## ACCEPTANCE_CRITERIA

- Download concurrency settings of 2 and 4 are verified without changing worker count to simulate MP4 serialization.
- For both settings, MP4 remux/conversion is globally limited to one active job; lock acquisition failure, wait, cancellation, release, and duplicate-job behavior fail safely.
- Insufficient space at download start/resume or remux time, ENOSPC during remux, and retry suppression are tested; no redundant TS fallback is produced on ENOSPC.
- Recoverable source fragments and task/resume state remain intact after FFmpeg, storage, NAS/publish-validation, collision, cancellation, restart, or duplicate-task failures.
- MP4 conversion success is distinct from verified final storage; `.parts` cleanup is disallowed until final-storage verification succeeds.
- Existing normal download, HLS resume, duplicate protection, normal MP4/TS fallback, NAS publish protections, UI/API compatibility, and final Docker patch behavior pass applicable offline regression checks.
- The four real failed jobs are not accessed or modified; production changes, retries, NAS writes, and data deletions remain zero.
- Unverified properties are reported as UNKNOWN; registration readback precedes code work.

## EVIDENCE

- User approved DL-001 code implementation and offline validation, but not deployment or operational recovery, on 2026-10-17.
- User-approved incident evidence concerns four ENOSPC-failed jobs with existing fragments. This registration phase does not access or modify those operational files; detailed incident facts remain user-supplied until independently verified within a separately permitted read-only investigation.
- Governance and Downloader shared registration was read back from canonical `teddy-subtitle-stage11` at `eebe6a22f2d102e85e4638c21a91f0a1189c4c4e`; Governance participation was then closed, leaving this Downloader task active alone.

## NEXT_DECISION

Review the implementation candidate and offline validation. Any production deployment, service change, retry/recovery of the four real jobs, NAS transfer, or data cleanup requires a separate explicit user approval.
