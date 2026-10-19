# Downloader non-subtitle workstream — active work

WORKSTREAM: downloader
TASK_ID: DLDWS-001
STATUS: IN_PROGRESS
CONTRACT_VERSION: 1.0.0
REQUIRES_WORKSTREAMS: downloader,discovery-writer-safety

## OBJECTIVE

Coordinate with Discovery Writer Safety to investigate the Writer smoke failure that blocks the DL-001 Docker build candidate, while preserving the existing Downloader implementation candidate, its download/MP4/ENOSPC goals, and all existing evidence.

## APPROVED_SCOPE

- Read-only compare the preserved DL-001 candidate and DWS-001 B-option candidate, identify the Writer smoke failure mechanism, and distinguish inode reuse from an unsafe active-socket path replacement or unlink.
- Reuse verified DWS-001 B-option findings without copying or overwriting either existing candidate wholesale.
- Preserve the DL-001 download-concurrency, globally serialized MP4, ENOSPC, fragment-retention, and offline-smoke work recorded in the archived DL-001 record.
- Prepare a reviewable proposal for isolated, synthetic offline regression coverage and an isolated Docker build-candidate verification path, including the exact boundaries and expected evidence.
- Keep every Writer active-socket, ownership, mode, collision, and path-replacement safety assertion. A failing regression must remain visible as a failure.

## PROHIBITED_SCOPE

- This registration execution authorizes no product-code or test edits, no product-specific test execution, and no Docker build. A later execution must explicitly authorize any such work and name its candidate/worktree and validation boundary.
- Do not remove, weaken, skip, mock away, or rewrite a failing safety check to manufacture a pass.
- Do not modify the existing dirty DL-001 worktree or the DWS-001 B candidate; preserve both as evidence.
- Do not run real downloads/retries/recovery, alter `.parts`, TS/MP4 files, task state, NAS/Jellyfin, production services, Writer sockets, or Stage11 artifacts.
- No deployment or operational changes. Do not reset, clean, rebase, merge, or force-push.

## ACCEPTANCE_CRITERIA

- The Writer smoke root cause is tied to exact candidate source and test evidence; inode reuse possibility is reported separately from any observed unsafe socket-path replacement.
- Existing DL-001 work and DWS-001 B-option candidate remain intact and independently identifiable.
- A proposed offline test matrix retains active-listener, replacement, ownership, mode, cleanup, and restart protections; all unknown outcomes remain UNKNOWN.
- Any future code/test or Docker candidate validation is explicitly authorized before execution, isolated from production, and reported independently from product or operational readiness.
- After the separate Governance closure, Downloader and Discovery Writer Safety both show `IN_PROGRESS / DLDWS-001`, contract version `1.0.0`, and exactly `downloader,discovery-writer-safety` in `REQUIRES_WORKSTREAMS`; no Stage11 field or artifact changes.

## EVIDENCE

- The complete prior `DL-001` active record, including its objectives, constraints, candidate references, test evidence, and unresolved items, is preserved byte-for-byte in `docs/governance/history/DLDWS-001-registration-base-34dede0/downloader-ACTIVE_WORK.md` (base blob `c336f560c6759cb6447309d0bac5826af0f5dac9`).
- The preserved DL-001 candidate is recorded at HEAD `30fb83e1c6b2a80eee67cef5bac8192bf6fa719b` in `/tmp/downloader-dl001-implementation-20261017`; its worktree is dirty and must not be changed. Its two isolated Python 3.10 synthetic smoke scripts previously passed, but the full Docker build remains NOT_RUN.
- The recorded DL-001 Writer smoke contains stronger socket-type, `0660` mode, and effective-UID checks in two cases, but retains a third nondeterministic `replacement_identity != stale_race_identity` assertion. Exact safe integration remains unverified.
- The DWS-001 B candidate `b0831048b3788b9a86a180f040b0152145a079c7` has separate offline evidence recorded in the paired workstream. That evidence does not establish DL-001 integration or Docker build success.
- The registration-phase commit `6014164c395be31fe4bb30c32062e1a3be08d37f` was read back with Governance, Downloader, and Discovery Writer Safety participating. After the separately verified Governance closure, this DLDWS-001 task requires only Downloader and Discovery Writer Safety.
- Registration preflight at base `34dede0af5bc205ff11af4275727e11627de680b` passed for the existing DL-001 task; baseline did not run the Docker build.

## PREVIOUS_STAGE_NEXT_DECISION

After exact remote registration readback, perform a read-only, SHA-pinned comparison of the Writer smoke paths and document the failing assumption and proposed isolated regression matrix. Request explicit execution authorization before editing/running tests or building a Docker candidate.


## SEPARATE APPROVED EXECUTION — Writer socket-activation production transition

APPROVAL_DATE: 2026-10-19
AUTHORIZATION: Explicit user approval in the DLDWS-001 Writer operations transition request.
EXECUTION_STATUS: BLOCKED_PREFLIGHT; the existing missav-dlp-web client container is exited (137), so its approved client-health path is unavailable. No Writer operations were changed.

This is a separately approved, one-time DLDWS-001 execution phase. It authorizes only transition of the Discovery Writer service to the exact socket-activation candidate and read-only client health validation. It does not authorize the Downloader Docker deployment or any download recovery.

### AUTHORIZED_SCOPE

- Use only the immutable Writer package candidate at `/tmp/dldws001-writer-release-package-20261019`, with entry-point SHA-256 `709999d4c10701a284a9e96f7facdf3b41ac3179fd5bf944c6cb8bf400fbf83d`. Verify all six package files against `PACKAGE_MANIFEST.tsv`.
- Stage those files only at `/opt/missav-dlp-web/teddy-library-discovery-writer/releases/sha256-709999d4c10701a284a9e96f7facdf3b41ac3179fd5bf944c6cb8bf400fbf83d/`. Do not overwrite an existing release; any mismatch is a stop condition.
- Use only `/tmp/dldws001-systemd-ops-candidate-20261019/units/teddy-library-discovery-writer.socket` and `units/teddy-library-discovery-writer.service.d/30-systemd-socket-activation.conf` for the systemd transition.
- After all preflight checks pass and backups are verified, stop the existing Writer service, confirm its process and listener have exited, remove only the confirmed-stale exact Writer socket pathname if required, install the two candidate unit files, run static verification and `daemon-reload`, enable and start the socket unit before the Writer service, and preserve the existing Writer service enabled state.
- Perform only read-only service/socket inspection and read-only Writer health requests, including through the existing Docker client path. Keep the current service identity, group access, and Downloader container unchanged.
- If any required preflight, backup, or post-transition check is UNKNOWN or fails, stop before the first service stop or follow the approved rollback procedure. If safe socket ownership or liveness is uncertain at any point, do not unlink it; use `BLOCKED_MANUAL_RECOVERY`.

### REQUIRED_PREFLIGHT_AND_BACKUP

Before stopping the service, verify and preserve: current service health; effective ExecStart, user/group and all drop-ins; service/socket enablement and active state; Writer socket and parent directory ownership, modes, and listener identity; client GID 988 and read-only socket mount; absence of in-flight Writer work; all six package hashes, import and `--help`; candidate unit syntax and merged-setting compatibility; previous release and service files. Store exact unit/drop-in copies, metadata, and hashes in a restricted operations backup location and verify the restoration commands before proceeding. Any unverifiable item blocks the transition.

### ACCEPTANCE_AND_BOUNDARIES

- Writer service is active with the pinned SHA release and `--systemd-socket`; the socket unit is listening with `Accept=no` and FD name `writer`.
- Socket is `root:teddy-library-discovery-writer`, mode `0660`; parent directory is mode `0750`; the existing GID 988 client path can complete a read-only health request.
- Existing Writer health succeeds locally and through the existing client path; logs show no startup error or socket path replacement/deletion issue.
- On any failed required check, stop the new units safely, restore the backed-up units, drop-ins, prior ExecStart and service/socket enabled and active state, and verify prior client health. Never force-remove an active or uncertain socket.
- This one-time approval overrides only earlier registration-phase prohibitions against the exact Writer service, socket, systemd, and read-only health actions listed above. It does not authorize Downloader container replacement/restart, downloads/retries/recovery, DB writes, changes to `.parts`, TS/MP4, NAS/Jellyfin, Stage11, existing DL-001/DWS-001 candidates, or unrelated product code; all other prior boundaries remain in force.
- No Docker build or product Git merge is part of this operations transition.

## NEXT_DECISION

Resume only after separate explicit authorization makes the existing client-health path available for read-only validation. Then repeat the full preflight and verify the restricted rollback backup. Do not stop the Writer service until every preflight item and rollback path passes.
