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

## SEPARATE APPROVED EXECUTION — Writer socket-activation final production transition

APPROVAL_DATE: 2026-10-19
AUTHORIZATION: Explicit user authorization in the final DLDWS-001 Writer operations transition request.
EXECUTION_STATUS: AUTHORIZED; preflight pending; no production operation has started.
PRIOR_BLOCK_OVERRIDE: The user accepts the previously passed read-only host GID 988 health check and previously passed isolated Docker health probe as substitutes only for health through the exited missav-dlp-web client before transition. This does not waive any other required preflight or rollback check.

This is a one-time DLDWS-001 Writer operations phase. The existing task remains active in Downloader and Discovery Writer Safety with contract version 1.0.0 and `REQUIRES_WORKSTREAMS: downloader,discovery-writer-safety`. This approval supplements the earlier transition record; it does not erase its `BLOCKED_PREFLIGHT` evidence or authorize general Downloader validation.

### PINNED_CANDIDATES

- Writer package source: `/tmp/dldws001-writer-release-package-20261019`; verify all six manifest entries and their SHA-256 values. The entry-point SHA-256 is `709999d4c10701a284a9e96f7facdf3b41ac3179fd5bf944c6cb8bf400fbf83d`.
- Immutable target release: `/opt/missav-dlp-web/teddy-library-discovery-writer/releases/sha256-709999d4c10701a284a9e96f7facdf3b41ac3179fd5bf944c6cb8bf400fbf83d/`. Do not overwrite an existing file or release; a mismatch blocks the transition.
- systemd candidates: `/tmp/dldws001-systemd-ops-candidate-20261019/units/teddy-library-discovery-writer.socket` and `units/teddy-library-discovery-writer.service.d/30-systemd-socket-activation.conf` only. Their installation targets are `/etc/systemd/system/teddy-library-discovery-writer.socket` and `/etc/systemd/system/teddy-library-discovery-writer.service.d/30-systemd-socket-activation.conf`.
- The existing `missav-dlp-web` container must remain exited and unchanged. It is not the Writer client-health test target and must never be started, restarted, replaced, or modified in this phase.

### REQUIRED_PREFLIGHT_AND_BACKUP

Before the first Writer service stop, verify all of the following: the existing Downloader container remains exited with the pinned local image; current Writer service health is READY; effective ExecStart, process identity, group, all drop-ins, enablement and active states; socket path and parent ownership, modes, and listener identity; no in-flight Writer request or work; all six package hashes; merged systemd candidate compatibility; and the previous release and rollback path. Reuse the earlier successful host and isolated Docker health results only for the direct existing-client health condition. The full application integration test remains NOT_RUN.

Before stopping Writer, copy the exact existing unit/drop-in files and required prior-release references into a restricted operations backup location. Record hashes, ownership/modes, enabled/active states, prior ExecStart, and socket metadata. Read the backup back and verify the rollback commands and paths. If any item is missing, unreadable, or uncertain, do not stop Writer and report `BLOCKED_PREFLIGHT`.

### AUTHORIZED_SCOPE

- Stage only the six verified package files in the pinned immutable release path and verify the installed SHA-256 values.
- After every preflight and backup check passes, stop the existing Writer service, confirm the old process and listener have exited, and inspect the exact existing socket pathname. Remove only that exact file if it is conclusively stale and no active listener exists. Never delete an active or uncertain socket.
- Install only the two pinned systemd files, run static verification, perform `daemon-reload`, activate/listen on the socket unit, and start the Writer through the approved socket-activation configuration. Preserve the existing Writer service automatic-start policy.
- Verify the running release SHA/path, `--systemd-socket`, socket FD name `writer`, `Accept=no`, service/socket active state, socket owner/group/mode, parent mode, local read-only Writer health, logs, and socket path stability.
- After transition, run exactly one isolated Docker health probe using only image `sha256:da1e46073bb94b1f942b67b2fead20cc00656922b65f446ef7316b48d706aa0f`: `--rm`, `--network none`, `--read-only`, UID:GID `65534:65534`, supplementary GID `988`, all capabilities dropped, `no-new-privileges`, 128 MiB memory, 16 PIDs, 0.5 CPU, 15-second outer timeout, bytecode disabled, and only `/run/teddy-library-discovery-writer` mounted read-only. Override the entrypoint to `python`; never run the image's default bootstrap command. Send exactly one newline-terminated `{"protocol_version":1,"operation":"health"}` frame, accept only protocol version 1 and `READY`, and confirm `--rm` cleanup. No retry is authorized.
- If any post-transition check fails, perform only the recorded rollback. If listener state or socket ownership is uncertain, do not unlink; report `BLOCKED_MANUAL_RECOVERY`.

### PROHIBITED_SCOPE_AND_ACCEPTANCE

- No starting, restarting, replacing, or modifying the existing `missav-dlp-web` container; no Downloader image deployment or build.
- No download, retry, recovery, `.tasks.json`, `.parts`, TS/MP4, database, NAS/Jellyfin, Stage11, or existing DL-001/DWS-001 candidate changes.
- No product code/test changes, unrelated service changes, or full Downloader application validation. Actual application integration remains `NOT_RUN` even if the isolated Docker health request passes.
- This one-time approval overrides only the prior block on using the successful host and isolated Docker health evidence in place of direct health through the exited existing Downloader client, and the earlier prohibition on the exact Writer service/socket/systemd transition and one post-transition isolated Docker health probe defined above. All other boundaries remain in force.
- Success requires all pinned files, preflight and backup checks, Writer/systemd/socket checks, local health, and the single post-transition isolated Docker health readback to pass. A successful Writer transition does not establish Downloader product or container health.

## NEXT_DECISION

Proceed only while both workstream copies contain this exact approval section and the full preflight plus verified rollback backup pass. On success, stop after reporting Writer results; keep the Downloader container exited and the full Downloader application integration explicitly NOT_RUN.

## PRIOR EXECUTION RESULT — Writer socket-activation final production transition (2026-10-19)

RESULT: FAIL; SYSTEMD_SOCKET: PASS_DURING_ATTEMPT; WRITER_HEALTH: READY_DURING_ATTEMPT; DOCKER_HEALTH: FAIL; ROLLBACK: PASS.

The candidate socket-activation service was started and passed its local Writer health and socket checks. The one post-transition isolated Docker probe sent an incorrectly escaped frame; the Writer returned `PROTOCOL_INVALID` before request dispatch. This was a probe framing failure, not evidence that the candidate health operation reached the database. The temporary Docker container was removed. The existing `missav-dlp-web` container remained exited (137) with image `sha256:da1e46073bb94b1f942b67b2fead20cc00656922b65f446ef7316b48d706aa0f`.

The approved rollback stopped the candidate service and socket, verified that no listener remained and that the exact socket pathname was stale, removed only `/run/teddy-library-discovery-writer/writer.sock`, removed the candidate socket unit and service drop-in, and restored the prior direct-mode service configuration and enabled state. The prior Writer service was active again with local health READY; the socket-activation unit is not installed. The six-file candidate release remains staged at its pinned release path but is unused. The restricted rollback backup at `/var/backups/dldws001-writer-transition-20261019` was preserved and read back. No database write, download operation, or download-data change occurred.

## SEPARATE APPROVED EXECUTION — corrected one-time Docker Writer health probe

APPROVAL_DATE: 2026-10-19
AUTHORIZATION: Explicit user approval in the DLDWS-001 Docker Health newline-fix and one-time recheck request.
EXECUTION_STATUS: PASS; the corrected frame preflight and single isolated Docker health probe passed; Writer production transition remains rolled back and is not authorized to resume.

This is a separate, single read-only health probe against the existing Writer socket. It supplements the prior failed transition and successful rollback evidence without changing either result. It does not authorize another Writer transition attempt.

### AUTHORIZED_SCOPE

- Before execution, read-only verify the canonical task authorization, the existing `missav-dlp-web` container is still exited (137), the exact local image ID is `sha256:da1e46073bb94b1f942b67b2fead20cc00656922b65f446ef7316b48d706aa0f`, the old direct-mode Writer is active and health READY, the socket permissions permit supplementary GID 988, and no temporary probe container/name collision remains.
- Generate the sole request payload using `json.dumps({"protocol_version": 1, "operation": "health"}, separators=(",", ":")).encode("utf-8") + bytes([10])`. Before any socket connection, verify exact payload bytes, final byte 10, and exactly one byte 10. Use the same Python source for local frame-only preflight and the Docker probe; the local preflight performs no socket I/O.
- Run exactly one `docker run --rm` using only the exact already-local image ID above, with `--network none`, `--read-only`, UID:GID `65534:65534`, supplementary GID `988`, all capabilities dropped, `no-new-privileges`, 128 MiB memory, 16 PIDs, 0.5 CPU, 15-second outer timeout, and bytecode generation disabled. Bind-mount only `/run/teddy-library-discovery-writer` read-only at the same path.
- Explicitly use `--entrypoint python` and only standard-library `-c` code. Do not run the image's default bootstrap command or copy the existing container's environment, volumes, or settings.
- Send exactly one `sendall(payload)`, with a five-second socket I/O timeout and maximum response size 4096 bytes. Require a newline-terminated response with `protocol_version == 1` and `status == "READY"`. Do not retry on any failure.
- Verify the temporary container is removed and the existing container, Writer PID, socket metadata, and systemd state remain unchanged after the probe.

### PROHIBITED_SCOPE

- No Writer service/socket/systemd changes or socket-activation transition retry.
- No starting, restarting, replacing, or modifying the existing `missav-dlp-web` container; no Docker build or pull and no additional probe container.
- No database mutation, downloads/retries/recovery, `.tasks.json`, `.parts`, TS/MP4, NAS/Jellyfin, or Stage11 changes.
- A successful health probe does not establish full Downloader application integration and does not authorize resuming Writer production transition.

This approval overrides only prior prohibitions to the extent required for this single corrected isolated Docker health probe. All other boundaries remain in force.

### EXECUTION_RESULT

FRAME_PREFLIGHT: PASS. REQUEST_FRAME_HEX: `7b2270726f746f636f6c5f76657273696f6e223a312c226f7065726174696f6e223a226865616c7468227d0a`; final byte 10; newline count 1. Frame preflight made no socket connection.
HOST_WRITER_HEALTH: READY. DOCKER_HEALTH: READY; exactly one `docker run` with the pinned image returned `{"protocol_version":1,"status":"READY"}`. TEMP_CONTAINER_CLEANUP: PASS.
EXISTING_CONTAINER: `missav-dlp-web` remained exited (137) with the pinned image. WRITER PID 43713, socket path/inode/owner/group/mode, parent-directory metadata, and systemd socket-unit state were unchanged. No Writer transition was retried; no database-mutation request or download operation was sent.
WRITER_DEPLOYMENT: ROLLED_BACK_UNCHANGED. This probe does not establish full Downloader application integration or authorize resuming the production transition.

## SEPARATE APPROVED EXECUTION — final Writer operations transition retry (one time)

APPROVAL_DATE: 2026-10-19
AUTHORIZATION: Explicit user approval in the DLDWS-001 Writer operations final one-time retry request.
EXECUTION_STATUS: PASS; the single authorized Writer transition and its one post-transition Docker health check passed.
RETRY_LIMIT: Exactly one transition attempt; consumed. Preserve the prior transition failure and rollback, and the corrected Docker health PASS recorded above.

This is a separately approved Writer-only operations attempt. It does not authorize Downloader container startup, deployment, rebuild, download work, database writes, or Stage11 changes. Publish this approval in both workstreams and verify exact remote readback before any Writer service stop.

### PINNED_CANDIDATES

- Writer package: `/tmp/dldws001-writer-release-package-20261019`; entry-point SHA-256 `709999d4c10701a284a9e96f7facdf3b41ac3179fd5bf944c6cb8bf400fbf83d`. The six-file package manifest and installed immutable release must match exactly. Do not recopy matching files or overwrite any mismatch.
- Installed release: `/opt/missav-dlp-web/teddy-library-discovery-writer/releases/sha256-709999d4c10701a284a9e96f7facdf3b41ac3179fd5bf944c6cb8bf400fbf83d/`.
- systemd candidates: `/tmp/dldws001-systemd-ops-candidate-20261019/units/teddy-library-discovery-writer.socket` and `/tmp/dldws001-systemd-ops-candidate-20261019/units/teddy-library-discovery-writer.service.d/30-systemd-socket-activation.conf` only.
- Docker health image: `sha256:da1e46073bb94b1f942b67b2fead20cc00656922b65f446ef7316b48d706aa0f`; the existing `missav-dlp-web` container must remain exited and unchanged.
- Reuse only the previously passing Python source `/tmp/dldws001-health-client-20261019.py`, SHA-256 `b2fe18b32631e8b6f0ccc2e8026c29649c87d6e50b032253d7b58b29bceb12ee`, and the prior validated argument array recorded below. Do not rewrite its frame generation or build a shell-escaped substitute.

### REQUIRED_PREFLIGHT_AND_BACKUP

- Confirm current Writer service health, effective ExecStart, identity, drop-ins, enablement/active state, listener, socket and parent metadata, GID 988 access, absence of in-flight work, and unchanged exited Downloader container.
- Verify all six package files and hashes against the manifest. If the immutable installed release already matches, leave it in place; a mismatch blocks without overwrite.
- Verify the exact two systemd candidates and static syntax. Inspect and read back the existing rollback backup at `/var/backups/dldws001-writer-transition-20261019`; do not overwrite it.
- Record the current live service/systemd/socket state in a new restricted, non-existing backup path if it differs from the existing rollback backup. Read back the copies, hashes, metadata, and restoration procedure. Do not stop Writer until rollback is verified.
- Before stopping Writer, compile the pinned health source without socket I/O and assert the exact frame hex `7b2270726f746f636f6c5f76657273696f6e223a312c226f7065726174696f6e223a226865616c7468227d0a`, final byte 10, and one newline byte. Verify the probe container name is free and the exact image is local.

### AUTHORIZED_SCOPE

- After canonical approval readback and every preflight/backup check passes, perform exactly one transition using only the pinned package and two systemd files. Preserve existing service automatic-start policy. Never remove a socket with an active listener or uncertain identity.
- Verify service health, running file SHA, `--systemd-socket`, active/listening socket unit, `FileDescriptorName=writer`, `Accept=no`, socket `root:teddy-library-discovery-writer` mode `0660`, and parent mode `0750`.
- After those checks, run exactly one isolated Docker health probe using the pinned image and the unchanged source SHA above. Reuse this validated argument array: `timeout --signal=TERM --kill-after=1s 14s docker run --rm --name dldws001-health-newline-20261019 --network none --read-only --user 65534:65534 --group-add 988 --cap-drop ALL --security-opt no-new-privileges --memory 128m --memory-swap 128m --pids-limit 16 --cpus 0.5 --env PYTHONDONTWRITEBYTECODE=1 --mount type=bind,source=/run/teddy-library-discovery-writer,target=/run/teddy-library-discovery-writer,readonly --entrypoint python sha256:da1e46073bb94b1f942b67b2fead20cc00656922b65f446ef7316b48d706aa0f -c <the exact pinned source>`. The source sends one `sendall(payload)`, uses a five-second socket timeout and 4096-byte response limit, and accepts only protocol 1 READY. Verify automatic temporary-container cleanup.
- If a post-transition check fails, use the verified current-state backup to perform the specified rollback once; never retry the transition. If socket state is uncertain, stop and report `BLOCKED_MANUAL_RECOVERY` without unlinking.

### PROHIBITED_SCOPE

- Do not start, restart, replace, or modify the existing `missav-dlp-web` container. No Docker image build, pull, or Downloader deployment.
- No downloads, retries, recovery, `.tasks.json`, `.parts`, TS/MP4, database writes, NAS/Jellyfin, or Stage11 access/change.
- No product code or test changes, no edits to protected DL-001/DWS-001 candidates, no unrelated service/systemd changes, and no second transition attempt.
- The passed isolated health request does not prove full Downloader application integration.

This one-time approval overrides only the earlier block against retrying the exact Writer transition and its defined post-transition Docker health check. All other boundaries remain in force.

### EXECUTION_RESULT

WRITER_DEPLOYMENT: PASS. SYSTEMD_SOCKET: PASS. WRITER_HEALTH: READY. DOCKER_HEALTH: READY. ROLLBACK: NOT_NEEDED.
FRAME_HEX: `7b2270726f746f636f6c5f76657273696f6e223a312c226f7065726174696f6e223a226865616c7468227d0a`; final byte 10; newline count 1. The previously validated source SHA-256 `b2fe18b32631e8b6f0ccc2e8026c29649c87d6e50b032253d7b58b29bceb12ee` was reused unchanged for the frame-only preflight and exactly one Docker `run`; response was protocol 1 READY and the temporary container was removed.
WRITER_SHA256: `709999d4c10701a284a9e96f7facdf3b41ac3179fd5bf944c6cb8bf400fbf83d`. All six installed release files matched the package manifest; no recopy was needed.
The service is active on the pinned `--systemd-socket` release; the socket unit is enabled and listening with `Accept=no`, `FileDescriptorName=writer`, and socket `root:teddy-library-discovery-writer` mode `0660`; parent directory is mode `0750`. Existing service enabled state remains enabled. No startup errors or path replacement markers were found.
The existing `missav-dlp-web` container remains exited (137) with its pinned image. No download, database mutation, or Stage11 operation was performed. Full Downloader application integration remains NOT_RUN.
Operational files changed: `/etc/systemd/system/teddy-library-discovery-writer.socket`, `/etc/systemd/system/teddy-library-discovery-writer.service.d/30-systemd-socket-activation.conf`, and the socket enablement symlink. Current-state rollback snapshot: `/var/backups/dldws001-writer-final-retry-20261019` (root-owned mode 0700; file hashes and readback verified). The pre-existing rollback backup remains preserved.

NEXT_DECISION: Stop after this Writer transition. Full Downloader application integration and Downloader container deployment remain outside this approval and require separate authorization.
