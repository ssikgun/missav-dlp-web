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

- 2026-10-19: User CT108 read-only DL-001 candidate audit: `/tmp/downloader-dl001-implementation-20261017`, branch `codex/dl001-implementation-20261017`, HEAD `30fb83e1c6b2a80eee67cef5bac8192bf6fa719b`, origin `ssikgun/missav-dlp-web` expected. Local dirty candidate preserved (5 modified + 6 untracked paths); `git diff --check` RC=0. Candidate Dockerfile has original Writer smoke at line 58, existing remux patch line 75, new MP4-queue check line 116; full isolated Docker build NOT_RUN/NOT_VERIFIED. Existing preserved Docker context archive is 1.7 MB with SHA-256 `fdbf89e44deb367504cc816a7d190021532d8ae4e10f1d5a6724b264bff22ca6`; contents not inspected. Crucial: local DL-001 Writer smoke Git blob `7ef62313b570f69d0aa1e84680bb794c455e57a9` differs from isolated DWS-001 revised-and-tested Writer smoke Git blob `bb137676f52657014dc85664fe0187aade869a01` at candidate `b6a623821de609072613540dc89db67eb1854484`. The exact textual difference and safety implications remain UNKNOWN pending read-only diff; do not overwrite/merge, Docker build or touch production files.

- 2026-10-19: User CT108 SHA-verified read-only diff of DL-001 local Writer smoke blob `7ef62313b570f69d0aa1e84680bb794c455e57a9` and DWS-001 smoke `bb137676f52657014dc85664fe0187aade869a01` returned expected DIFF_RC=1. DL-001 file already preserves 0660 socket mode and effective-UID owner checks in the restart/stale-rebind cases (stronger than DWS at the time) and lacks the first two insecure inode-inequality asserts. DL-001 still has the third nondeterministic assert `replacement_identity != stale_race_identity` in a legacy active-replacement race smoke, which can destabilize its Docker build. The DWS candidate independently restored the permission/owner checks at `b0831048b3788b9a86a180f040b0152145a079c7`. Do NOT copy the DWS smoke wholesale over DL candidate or mutate the dirty DL worktree; this observation is read-only only. No Docker build was run. The exact cross-workstream smoke integration and safe isolated build verification remain to be determined without violating DWS/DL workstream scope.

- 2026-10-19: User CT108 READ-ONLY Python AST/file-reference audit in preserved dirty candidate `/tmp/downloader-dl001-implementation-20261017` passed exact parent HEAD `30fb83e1c6b2a80eee67cef5bac8192bf6fa719b`. Six local DL-001 candidate modules/scripts parsed successfully (SYNTAX=PASS for `teddy_mp4_queue.py`, `teddy_mp4_queue_smoke.py`, `teddy_download_safety.py`, `teddy_download_safety_smoke.py`, `teddy_patch_mp4_queue.py`, `teddy_patch_download_safety.py`). User log reports module SHA256s; both smoke programs use TemporaryDirectory fixtures, but also reference subprocesses and filesystem writes/removals; source reference listing alone does NOT prove their active paths are sandboxed. `READ_ONLY_SOURCE_AUDIT=COMPLETE` indicates inspection only, not execution. Before an offline smoke run, inspect the main test entrypoints and subprocess/SSH publication fixture mocking. No production, build, or operational change.

## NEXT_DECISION

Review the implementation candidate and offline validation. Any production deployment, service change, retry/recovery of the four real jobs, NAS transfer, or data cleanup requires a separate explicit user approval.
