# Discovery Writer Safety workstream — active work

WORKSTREAM: discovery-writer-safety
TASK_ID: DLDWS-001
STATUS: IN_PROGRESS
CONTRACT_VERSION: 1.0.0
REQUIRES_WORKSTREAMS: downloader,discovery-writer-safety

## OBJECTIVE

Share DLDWS-001 with Downloader to safely investigate the Writer socket smoke failure blocking the DL-001 Docker build candidate, preserving the approved B-option candidate and the distinction between inode reuse and actual socket replacement safety.

## APPROVED_SCOPE

- Read-only review the existing DWS-001 B-option candidate, its isolated smoke evidence, the legacy direct-mode race results, and the DL-001 Writer smoke evidence.
- Preserve the exact B-option candidate and its existing test evidence; do not copy it wholesale into the DL-001 candidate.
- Identify which failures arise from unreliable inode-inequality assumptions and which demonstrate an actual unsafe path replacement or active-socket unlink.
- Propose isolated synthetic offline regression cases that preserve active-listener protection, replacement detection, socket ownership and mode, cleanup boundaries, and restart safety.
- Keep deployment compatibility, cold-start parent-directory ownership, and any other unverified systemd behavior explicitly UNKNOWN.

## PROHIBITED_SCOPE

- This registration execution authorizes no Writer product-code or test changes, no product-specific test execution, and no Docker build. A later execution must explicitly authorize any such work and name its candidate/worktree and validation boundary.
- Do not delete, relax, bypass, skip, or redefine any safety test or turn a reproduced failure into a pass.
- Do not change the existing B-option candidate, DL-001 candidate, live Writer service/socket, systemd units, databases, or operational files.
- No Docker build, download, retry, remux, recovery, NAS/Jellyfin access or change, Stage11 change, or deployment.
- Do not reset, clean, rebase, merge, or force-push.

## ACCEPTANCE_CRITERIA

- Socket inode reuse as a possible filesystem behavior and actual socket-path replacement/unlink safety are assessed and reported separately.
- Prior B-option evidence is retained with its exact candidate SHA; a scoped smoke PASS is never presented as complete production or cross-workstream safety.
- The proposed isolated synthetic matrix retains active listener, replacement-before-unlink, ownership, mode, restart, and no-unlink checks without weakening prior coverage.
- Unverified systemd lifecycle and deployment properties remain UNKNOWN until separately authorized and tested.
- After the separate Governance closure, Downloader and Discovery Writer Safety both show `IN_PROGRESS / DLDWS-001`, contract version `1.0.0`, and exactly `downloader,discovery-writer-safety` in `REQUIRES_WORKSTREAMS`; Stage11 remains independent and unchanged.

## EVIDENCE

- The complete prior `DWS-001` active record, candidate history, and verification evidence are preserved byte-for-byte in `docs/governance/history/DLDWS-001-registration-base-34dede0/discovery-writer-safety-ACTIVE_WORK.md` (base blob `d1d6316280cac5b87ad3de4a0c4dfacf10298d91`).
- The B-option candidate is `b0831048b3788b9a86a180f040b0152145a079c7`. User-provided isolated runs report syntax, legacy smoke, and socket-activation smoke PASS at that SHA. These are scoped offline results only.
- The registration-phase commit `6014164c395be31fe4bb30c32062e1a3be08d37f` was read back with Governance, Downloader, and Discovery Writer Safety participating. After the separately verified Governance closure, this DLDWS-001 task requires only Downloader and Discovery Writer Safety.
- Direct-mode pre-unlink replacement and simulated identity-collision evidence remain safety FAIL findings. Actual inode reuse was not observed in the recorded trials; its possibility remains distinct from the observed unsafe path replacement.
- Socket-unit static syntax verification passed for the recorded candidate, but full service/socket integration, clean-start directory ownership, and production suitability remain unverified. The Docker build and DL-001 integration remain NOT_RUN.
- Registration preflight at base `34dede0af5bc205ff11af4275727e11627de680b` passed for the existing DWS-001 task.

## PREVIOUS_STAGE_NEXT_DECISION

After exact remote registration readback, perform a read-only, SHA-pinned comparison with the DL-001 smoke and produce the cross-workstream failure analysis. Request explicit execution authorization before changing or running Writer tests, product code, or a Docker build candidate.


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

## SEPARATE APPROVED EXECUTION — one-time isolated Docker Writer health probe

APPROVAL_DATE: 2026-10-19
AUTHORIZATION: Explicit user approval in the DLDWS-001 one-time isolated Docker Writer health probe request.
EXECUTION_STATUS: AUTHORIZED; the separate Writer production transition remains BLOCKED_PREFLIGHT.

This separate approval authorizes creation and removal of exactly one temporary, isolated Docker client container for exactly one read-only health request to the existing Writer socket. It does not authorize starting, restarting, or replacing the existing missav-dlp-web container, changing the Writer service or socket, or resuming the production transition.

### AUTHORIZED_SCOPE

- Before the probe, verify the existing missav-dlp-web container is still exited; record its exact image ID, Config.User, GroupAdd, and socket mount; verify that exact image is already local and has no unexpected declared VOLUME.
- Verify the Writer service remains active and health-ready, the socket and parent directory ownership and modes, and that the unique probe container name is unused.
- Use only the exact local image ID referenced by the existing exited container. Do not build or pull an image.
- Run one docker run --rm temporary container with network disabled, a read-only root filesystem, UID:GID 65534:65534, supplementary GID 988, all capabilities dropped, no-new-privileges, 128 MiB memory, 16-process limit, 0.5 CPU limit, and a 15-second outer timeout.
- Bind-mount only /run/teddy-library-discovery-writer into the same path as read-only. Do not copy the existing container's volumes or environment. Override its entrypoint and command to run only Python standard-library code with bytecode generation disabled.
- Send exactly one newline-terminated request: {"protocol_version":1,"operation":"health"}. Bound connection/read time and response size. Accept only protocol_version 1 and status READY.
- Do not issue preflight_holding, mark_absent, or any database mutation request. Remove the temporary container automatically and verify its removal and that existing operational resources remain unchanged.

### PROHIBITED_SCOPE

- Starting, restarting, or modifying the existing missav-dlp-web container.
- Creating any additional container, building or pulling images, or changing Writer service/socket/systemd configuration.
- Downloads, retries, recovery, database writes, changes to download files, NAS/Jellyfin, or Stage11.
- Treating this isolated probe as existing-client health or as clearance for Writer production deployment.

This one-time approval overrides only prior prohibitions to the extent required for the single isolated Docker health probe above. All other boundaries remain in force.

### PRIOR EXECUTION RESULT — first isolated Docker attempt

RESULT: FAIL_BEFORE_REQUEST; HEALTH_RESPONSE: NOT_RUN.

The single prior attempt exited with code 127 because the image did not contain /usr/bin/python3. The Python process never started, so no socket connection or health frame was sent. The --rm container was removed. The existing missav-dlp-web container remained exited (137), and the Writer service and socket metadata were unchanged.

## SEPARATE APPROVED EXECUTION — one-time PATH-python Docker Writer health recheck

APPROVAL_DATE: 2026-10-19
AUTHORIZATION: Explicit user approval in the DLDWS-001 Docker Writer Health one-time recheck request.
EXECUTION_STATUS: PASS; one-time isolated health returned READY; Writer production transition remains BLOCKED_PREFLIGHT.
REEXECUTION_COUNT: exactly one retry is authorized after the prior entrypoint failure.

This authorization covers only one isolated Docker client run against the existing Writer socket. It does not authorize starting or changing the existing missav-dlp-web container, changing Writer operations, or resuming production transition.

### AUTHORIZED_SCOPE

- Use only the already-local image ID sha256:da1e46073bb94b1f942b67b2fead20cc00656922b65f446ef7316b48d706aa0f referenced by the existing missav-dlp-web container. Do not build or pull.
- Before execution, confirm the existing container remains exited, the exact image ID and PATH, GroupAdd 988 and read-only Writer socket mount, Writer service/PID and health, socket metadata, and absence of a probe-name collision or leftover prior temporary container.
- Run exactly one docker run --rm with network none, read-only root filesystem, UID:GID 65534:65534, supplementary GID 988, all capabilities dropped, no-new-privileges, 128 MiB memory, PIDs 16, CPU 0.5, and a 15-second total time limit.
- Bind-mount only /run/teddy-library-discovery-writer at the same path read-only. Do not inherit the existing container's volumes or environment. Set PYTHONDONTWRITEBYTECODE=1.
- Explicitly override the image entrypoint to python and the command to a Python standard-library -c program; do not execute the image's default CMD python teddy_bootstrap.py or import application/bootstrap code.
- Send exactly one newline-terminated request: {"protocol_version":1,"operation":"health"}. Limit socket I/O to 5 seconds and response size to 4096 bytes. Accept only protocol_version 1 and status READY.
- Do not issue preflight_holding, mark_absent, or any database mutation request. Rely on --rm and verify the temporary container is absent afterward; confirm the existing container and Writer service/socket state are unchanged.
- If this single retry fails or cannot start, stop without another attempt. A successful isolated probe does not establish health through the existing missav-dlp-web container and does not clear WRITER_DEPLOYMENT=BLOCKED_PREFLIGHT.

### PROHIBITED_SCOPE

- Starting, restarting, replacing, or modifying the existing missav-dlp-web container.
- Creating any additional container, building or pulling images, or changing Writer service/socket/systemd configuration.
- Downloads, retries, recovery, database writes, file cleanup, NAS/Jellyfin, or Stage11 changes.
- Treating this probe as production readiness or automatically resuming Writer transition.

This approval overrides only prior prohibitions to the extent needed for the single PATH-python Docker health recheck. All other boundaries remain in force.

### EXECUTION RESULT

RESULT: PASS; DOCKER_SOCKET_PROBE: PASS; HEALTH_RESPONSE: READY; TEMP_CONTAINER_CLEANUP: PASS.
IMAGE_ID: sha256:da1e46073bb94b1f942b67b2fead20cc00656922b65f446ef7316b48d706aa0f
PROCESS_IDENTITY: UID:GID 65534:65534; supplementary groups included GID 988.
HEALTH_FRAME_COUNT: 1; protocol_version: 1; status: READY.
EXISTING_CONTAINER: missav-dlp-web remained exited (137), unchanged.
WRITER_STATE: service PID and socket path/inode/ownership/mode unchanged.
WRITER_DEPLOYMENT: BLOCKED_PREFLIGHT; this probe does not authorize or resume production transition.
