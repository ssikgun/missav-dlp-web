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

## SEPARATE APPROVED EXECUTION — isolated Downloader startup validation and minimum safety fix

APPROVAL_DATE: 2026-10-19
AUTHORIZATION: Explicit user approval in the DLDWS-001 isolated startup validation and minimum safety fix request.
EXECUTION_STATUS: AUTHORIZED; no Downloader production deployment is authorized.

This is a separate DLDWS-001 execution phase. It authorizes isolated startup validation against synthetic data and, only if a concrete safety hazard or untestable side effect is confirmed, a minimal fix in a new isolated candidate. It preserves the completed Writer transition result and its evidence. It does not authorize operating the existing Downloader container.

### PINNED_INPUTS_AND_PRESERVATION

- Canonical base: `teddy-subtitle-stage11` at `1a91f4a8ae5785c3a2636e2c481c6b9a670de749`; active shared task remains `DLDWS-001`, contract `1.0.0`, requires `downloader,discovery-writer-safety`.
- Reuse only the existing integration image ID `sha256:c39ae7d47feddeb4c2df4bb6712eb5d61ffb59549c3c7f4ab26b19706d19a827`, tag `missav-dlp-web:dldws001-integration-20261019`, and its context/evidence at `/tmp/dldws001-integration-20261019`. Do not modify, rebuild, retag, or pull this image or context.
- Preserve the production `missav-dlp-web` container and image, `/opt/missav-dlp-web/work`, task/settings files, `.parts`, Writer service/systemd configuration, protected DL-001/DWS-001 candidates, Stage11, NAS, and Jellyfin.
- Create a new unique isolated candidate and synthetic test directory under `/tmp`; record source and output hashes. Do not copy production job names, URLs, secrets, DB state, or real fragments.

### AUTHORIZED_SCOPE

- Inspect the final runtime code in the pinned image and compare it with the integration context, accounting for Docker build-time patches.
- Create only synthetic test data representing four error tasks at retry count 30, `auto_retry=true`, `auto_retry_max=30`, `max_concurrent=2`, synthetic task IDs, fake `.parts` directories, small synthetic TS fragments, and minimum settings.
- Run the pinned image only in a disposable test container with no network, no published ports, no Writer socket/DB/NAS/download-data mounts, nonessential privileges removed, explicit resource and runtime limits, and writable paths restricted to the synthetic test directory. Verify process and temporary-resource cleanup.
- Record startup state changes and side effects: task-state reads/writes, temp cleanup, download/retry workers, MP4 recovery, proxy refresh/external connection attempts, health availability, and synthetic fragment preservation. Distinguish expected file serialization from data loss.
- Apply a minimal change only if the isolated evidence establishes a safety hazard or an untestable side effect. Make it in a separate candidate, preserve default normal startup/download/retry/MP4 behavior, and provide an explicit safe startup/health-only path if needed. Do not alter the pinned image or original integration candidate.
- Run only relevant offline synthetic regressions against the final patched runtime. A separate test-only image layer is permitted; preserve the original integration image tag and ID. Report any gap between the test layer and deployable Dockerfile integration.

### PROHIBITED_SCOPE

- No start/restart/create/recreate of production `missav-dlp-web`; no production image deployment, build, pull, or Compose edit.
- No mount, read, or write of production work data, `.tasks.json`, `.settings.json`, `.parts`, TS/MP4, operational DB, NAS, Jellyfin, Writer socket, or Stage11 data during isolated execution.
- No production downloads, retries, recovery, MP4 work, Writer/systemd changes, protected-candidate changes, or product-code merge/push to the canonical branch.
- Do not weaken, skip, delete, or bypass an existing safety test. If network isolation prevents startup, report the environment limitation rather than declaring a product defect.

### ACCEPTANCE_AND_NEXT_DECISION

- Preserve before/after synthetic task JSON and `.parts` evidence; identify each startup side effect and whether any synthetic data is altered or removed.
- Confirm whether retries/download workers, MP4 recovery, proxy/network activity, and health start; bound conclusions to the tested image and environment.
- If no fix is needed, preserve existing behavior and report `MINIMAL_FIX=NOT_NEEDED`. If a fix is made, show safe-mode behavior and relevant normal-mode regressions pass without changing normal startup semantics.
- Production deployment remains unapproved and requires a separate user decision.

NEXT_DECISION: Review the isolated result and decide separately whether to integrate the opt-in health-only mode into a deployable build. No production deployment is authorized.

### EXECUTION_RESULT — isolated Downloader startup validation (2026-10-19)

ISOLATED_STARTUP_TEST: PASS. The pinned base image and the test-only image's default mode both started with synthetic state and returned HTTP 200; the opt-in health-only mode returned protocol 1 READY. All test processes and temporary containers were cleaned up.
STARTUP_SIDE_EFFECTS: IDENTIFIED. Normal startup rewrites `.tasks.json` through `load_tasks()`/`save_tasks()`, performs legacy `.*.part.ts` cleanup, starts download workers and the retry monitor, creates and starts the MP4 queue recovery worker, and schedules proxy-pool refresh. Under network isolation the refresh completed with zero candidates; SpoofDPI startup failed because the isolated container lacks the required environment. The four synthetic jobs were already at retry limit, so no retry or download ran. The integrated safety patch preserved the eight task-linked `.parts` fragments.
DATA_PRESERVATION: PASS for the tested synthetic state. Safe mode preserved task/settings/proxy state and all fragment hashes byte-for-byte. Normal mode preserved task semantics and fragments; `.tasks.json` bytes changed from expected serialization. No production data was mounted or accessed.
MINIMAL_FIX: APPLIED only in `/tmp/dldws001-startup-validation-complete-20261019/candidate`. The opt-in `TEDDY_STARTUP_MODE=health-only` path returns `/healthz` READY and bypasses task/settings I/O, cleanup, proxy/SpoofDPI/MP4 installation, and download/retry worker startup. With the variable unset, the existing normal startup path remains active.
OFFLINE_REGRESSION: PASS with evidence scope recorded. The test-only image's health-only smoke, MP4 queue smoke (9 groups), and MP4 build verifier passed; the original integration image's DL-001 download safety smoke PASS was reused. A follow-up attempt to rerun that smoke against the final test-only layer stopped before assertions because its helper expects the pre-MP4-patch entrypoint stage; the test was not modified or weakened. See `candidate/evidence/download-safety-smoke-rerun.txt` in the isolated candidate.
TEST_ONLY_IMAGE: `missav-dlp-web:dldws001-startup-guard-test-20261019`, `sha256:2d0ab22770d25652f30919c8f75e3a560958944391ab0b3b021091d8c361c944`. The original integration image remains `sha256:c39ae7d47feddeb4c2df4bb6712eb5d61ffb59549c3c7f4ab26b19706d19a827`; all 470 original context files still match the recorded audit.
DEPLOYMENT_GATE: BLOCKED. The guard exists only in an isolated test-layer candidate and has not been integrated into the deployable Dockerfile. Production deployment remains unapproved.
OPERATIONS: NONE. The production Downloader container remains exited (137); Writer service/configuration, download data, database, NAS/Jellyfin, and Stage11 were not changed.

## SEPARATE APPROVED EXECUTION — deployable health-only integration and final offline regression

APPROVAL_DATE: 2026-10-20
AUTHORIZATION: Explicit user approval in the DLDWS-001 deployable health-only Docker integration and final regression request.
EXECUTION_STATUS: COMPLETED; isolated build and final-image regression finished. Production Downloader deployment and operational changes remain unauthorized.
SHARED_TASK: DLDWS-001
REQUIRED_WORKSTREAMS: downloader,discovery-writer-safety
CANONICAL_BASE: `teddy-subtitle-stage11` at `3f8a4499920e7bd6aa0014de60c10e8a82198063`.

### AUTHORIZED_SCOPE

- Create a new isolated candidate by hash-verifying and copying the preserved 470-file DL-001 integration context. Do not alter its original context, evidence, image tag, or image ID.
- Integrate only the already-validated opt-in `TEDDY_STARTUP_MODE=health-only` changes to `app.py` and `teddy_bootstrap.py` and their minimal Dockerfile build-stage hook. Verify patch order so later Downloader/MP4 patches do not overwrite the guard. Keep unset/default mode behavior unchanged.
- Build one new, uniquely tagged isolated Docker image; record inputs, final runtime source hashes, image ID, and build evidence.
- Run final-image isolated synthetic health-only and normal-startup compatibility checks with network disabled, no published ports, no production/Writer/DB/NAS mounts, and bounded resources. Run the relevant DL-001 safety and MP4 regressions at their correct patch stages; report tests executed on the final image separately from reused historical evidence.
- Preserve every test assertion. If a smoke helper cannot run against the final layer because it expects an earlier patch stage, report the limitation and its stage-correct alternative evidence without disabling or weakening the test.
- Record the execution result in both affected ACTIVE_WORK files and the canonical handoff after validation.

### PROHIBITED_SCOPE

- No start/restart/recreate/replace of production `missav-dlp-web`; no Compose change, operational image replacement, or deployment.
- No real downloads, retries, MP4 conversion, operational data/DB access, Writer service/socket/systemd changes, NAS/Jellyfin changes, or Stage11 changes.
- Do not modify the original integration context/image/evidence, prior health-only candidate, protected DL-001/DWS-001 worktrees, or production data.
- No weakening, skipping, deleting, or bypassing existing tests; no product-code merge/push to the canonical branch.

### ACCEPTANCE_AND_NEXT_DECISION

- Verify all copied source hashes against the preserved integration audit and verify the new final image contains the intended health-only runtime after the full patch chain.
- Verify `/healthz` READY and byte-identical synthetic state in health-only mode; verify default mode retains normal startup and synthetic `.parts` preservation without running a download.
- Report final-image MP4 regression and DL-001 safety regression separately, including exact test stage, results, or remaining incompleteness.
- Production resources remain untouched. A successful candidate build does not authorize production deployment.

NEXT_DECISION: Review the isolated result and decide separately whether to approve an operating backup, rollback and deployment procedure for the exact tested image.

### EXECUTION_RESULT — deployable health-only image (2026-10-20)

CANONICAL_APPROVAL_READBACK: PASS; the separate approval was read back from the canonical branch in both ACTIVE_WORK files before implementation at commit f206ba0e52d8c7280bc5f63e0909aec4dde82553.
DEPLOYABLE_IMAGE_BUILD: PASS; `missav-dlp-web:dldws001-deployable-startup-20261020`, image ID `sha256:83322ee82e736b5ba026b8d98d5709b9685ca9c6b051c2a7f4c7b9bf8d058573`.
HEALTH_ONLY: PASS; final-image `/healthz` returned protocol 1 READY, and the synthetic task/settings/proxy/fragment manifest stayed byte-identical. No worker or proxy-pool startup marker appeared.
NORMAL_STARTUP: PASS; final-image HTTP returned 200 with startup mode unset. The four capped synthetic errors retained their task meaning and all eight `.parts` fragments matched; `.tasks.json` bytes changed only through normal serialization. No retry or download ran. Network was disabled; normal startup's proxy refresh attempt could not access the network.
MP4_REGRESSION: PASS; final-image smoke passed all 9 groups with a 256 MiB synthetic `/tmp`.
DOWNLOAD_SAFETY_REGRESSION: PASS at Docker build stage 60/84, immediately after the DL-001 safety patch and before the MP4 patch, where the phase-sensitive existing smoke passed. The final post-patch image also passed the MP4 and final build verifiers; no assertion was removed or weakened.
FINAL_IMAGE_INTEGRITY: PASS; exact build context had 472 files, all 470 source files match the preserved audit, and the only changed original file was Dockerfile. Final runtime source SHA-256: `app.py=5912b09955493ce74919eb0e017f9e09a842e88ef30c778c9bfeee7b73676287`, `teddy_bootstrap.py=0bddf29291379fa01b529429303460f85e7c863887d856e99502d5e2e3ae87d4`, `teddy_entrypoint.py=a538f2087ff6466d60ee750551605087932d041ae1667f11951875fb02022916`, `teddy_mp4_queue.py=85e8078c9aa6f27f3ceae13f9202617d14133fa83a1e3cf06687b558e13a1767`, `teddy_proxy_pool.py=9076e7b1ffd94f7868ea3b80aaa3c226233978d8566b7bcc70f7b4c2afcdf41e`.
DOCKERFILE_REPRODUCIBILITY: NOT_DETERMINISTIC; floating base/uv tags, apt metadata, SpoofDPI main installer and lower-bound Python requirements can resolve differently later. The gate applies to this exact tested artifact; a later rebuild is not covered by these results.
DEPLOYMENT_GATE: READY for this exact image only. The image remains isolated and has not been published or deployed.
OPERATIONS: NONE. Production `missav-dlp-web` remains exited (137); no Compose, Writer, DB, download data, NAS/Jellyfin or Stage11 resource changed. Test containers and synthetic runtime fixtures were removed.

NEXT_DECISION: Review a separate operating backup, rollback and deployment procedure for this exact image. Production deployment still requires its own approval.

## SEPARATE APPROVED EXECUTION — Downloader production backup, rollback, and deployment-plan review

APPROVAL_DATE: 2026-10-20
AUTHORIZATION: Explicit user approval in the DLDWS-001 Downloader production backup, rollback, and deployment-plan final review request.
EXECUTION_STATUS: COMPLETED_READ_ONLY_REVIEW; production backup and deployment remain unauthorized.
SHARED_TASK: DLDWS-001
REQUIRED_WORKSTREAMS: downloader,discovery-writer-safety
CANONICAL_BASE: `teddy-subtitle-stage11` at `0ed3544fa8c944719c22cc8cbbaa3e86b2d36517`.
PINNED_CANDIDATE_IMAGE: `missav-dlp-web:dldws001-deployable-startup-20261020`, `sha256:83322ee82e736b5ba026b8d98d5709b9685ca9c6b051c2a7f4c7b9bf8d058573`.

This separate phase authorizes read-only inspection of the pinned local image, existing Downloader container, actual production Compose configuration, Writer integration state, and current data metadata; drafting and limited synthetic validation of backup, deployment, and rollback procedures; and recording the result in both workstream ACTIVE_WORK files and the canonical handoff. It does not authorize creating a production backup, changing production files or settings, stopping/starting/recreating/renaming/removing containers, deploying the candidate image, or changing Writer, DB, download data, NAS/Jellyfin, or Stage11.

### AUTHORIZED_SCOPE

- Confirm canonical identity and the matching DLDWS-001 approval in both required workstreams before operational inspection.
- Read only the exact candidate and current production image metadata; do not tag, pull, rebuild, prune, or delete images.
- Read only the existing container, actual Compose inputs and merged configuration, relevant auto-start configuration, Writer/socket state, and non-secret work-data metadata. Do not print secret values, URLs, task identifiers, or full download listings.
- Assess whether existing container identity can be retained, whether exact Compose/image settings are compatible, current retry/partial-file state, backup feasibility, and rollback boundaries.
- Produce a plan and limited verification evidence without writing to production resources. Existing image build and offline regression PASS evidence is reused and is not rerun.
- Append the final review result to both ACTIVE_WORK files and `docs/handoff/missav-dlp-web/CURRENT_HANDOFF.md`; no product code, contract, router, or Stage11 file may change.

### PROHIBITED_SCOPE

- Production backup creation or restore; any write to `/opt/missav-dlp-web/work`, Compose/env/unit files, task/settings/queue/fragment files, or databases.
- Downloader container start, stop, restart, recreate, rename, remove, or new operational container creation; no candidate image deployment.
- Downloads, retries, recovery, MP4 work, NAS/Jellyfin changes, Writer or systemd changes, Stage11 changes, product-code changes, image build/pull/prune/tag/delete, and Git product merge/push.
- Never treat `TEDDY_STARTUP_MODE=health-only` READY as proof that production task/settings data or Writer integration is safe.
- Do not allow ordinary startup before a verified backup and a task-specific retry/partial-file decision.

### ACCEPTANCE_CRITERIA

- Exact canonical head and approval readback are confirmed before operational inspection.
- Candidate image pin and the existing container/Compose/runtime/data facts are reported with secrets redacted.
- Backup and rollback plans specify source/destination, consistency, capacity/inode, metadata/symlink preservation, readback/restore verification, collision handling, and abort conditions without creating a production backup.
- Any unresolved container-identity, Compose compatibility, data safety, or retry control is reported as a deployment gate, not assumed away.
- Result records `PRODUCTION_BACKUP=NOT_RUN` and `PRODUCTION_DEPLOYMENT=NOT_RUN`; operations remain unchanged.

NEXT_DECISION: Finish the read-only production preflight and produce the plan; any actual backup or deployment requires separate explicit approval.

### EXECUTION_RESULT — Downloader production backup, rollback, and deployment-plan review (2026-10-20)

EXECUTION_STATUS: COMPLETED_READ_ONLY_REVIEW. Production backup and deployment remain unauthorized and NOT_RUN.
DEPLOYMENT_PLAN: BLOCKED; durable backup destination and container-identity decision remain unresolved.
IMAGE_PIN: PASS; exact local candidate tag and image ID match. Existing image ID also remains present.
COMPOSE_COMPATIBILITY: PASS; live three-file Compose configuration resolved using current inspect environment matched the exited container on image, service/name, restart, GID 988, port, all 14 mounts, and all 31 service environment keys; no secret values were recorded.
BACKUP_PLAN: BLOCKED; `/var/backups` shares the source `/dev/loop4` filesystem; `/tmp` is volatile tmpfs and cannot hold a verified archive-plus-restore. No approved separate persistent target was identified.
ROLLBACK_PLAN: BLOCKED; restore data has not been created or verified. Standard Compose image replacement recreates the existing container, so exact container ID preservation is not available in the standard path.
DATA_PROTECTION: UNKNOWN until an independent backup and restore check pass.
PRODUCTION_BACKUP: NOT_RUN. PRODUCTION_DEPLOYMENT: NOT_RUN.

OBSERVED_STATE: existing `missav-dlp-web` container ID `880cf97a6a3dece8e5ea51def22900c3aa41c32c2b73ba8f098c3025d7e9d4ca` remains `exited (137)` on image `sha256:da1e46073bb94b1f942b67b2fead20cc00656922b65f446ef7316b48d706aa0f`; candidate image is `missav-dlp-web:dldws001-deployable-startup-20261020`, `sha256:83322ee82e736b5ba026b8d98d5709b9685ca9c6b051c2a7f4c7b9bf8d058573`. Current production work has 4 ENOSPC-error tasks, each retry count 30; saved settings are `auto_retry=true`, cap 30, concurrency 2; four task-linked `.parts` directories contain 8,637 files / 16,996,662,891 bytes; no orphan parts, loose `.*.part.ts`, or MP4 queue task record was found. These current counts are read-only observations and must be rechecked before any later execution.

COMPOSE_INPUTS (actual order): `/opt/missav-dlp-web/compose.yaml`, `/tmp/e4b-web-image-override.yaml`, `/opt/missav-dlp-web/stage13-ui-24fc73a.override.yaml`. The Downloader service is `unless-stopped`, `58000:5000`, default bridge network, depends on the currently running `gluetun-missav`, and has a read-write `/downloads` bind plus read-only Writer socket mount and GID 988. `docker.service` is enabled/running; no Downloader-specific systemd unit was found. Writer service/socket remains active/listening with systemd socket FD `writer`, `Accept=no`, `0660`, parent `0750`; it was not changed.

BACKUP/DEPLOYMENT PLAN: first obtain an approved separate persistent destination with at least 40 GB free and 20,000 free inodes for archive plus scratch restore verification of the current partial set. After a separate execution approval, hold Docker auto-start in a known state, confirm the container is exited and no process changes `/opt/missav-dlp-web/work`, then archive only `.tasks.json`, `.settings.json`, `.proxy-pool.json`, and all direct-child `.*.parts` with numeric owner, ACL, xattr, sparse-file, and symlink preservation. Save Compose inputs and effective container metadata in a restricted location; do not expose environment values. Verify one archive checksum, private member-count/readback, and extraction into scratch before any ordinary start. Do not use `/var/backups` or `/tmp` for that purpose.

Before normal start, recheck there are no pending/running tasks, all error retries remain at cap, all parts are task-linked, loose temp files are absent, and MP4 queue state is empty. If any task is below retry cap while `auto_retry=true`, or any temp/orphan part exists, hold normal start; use the existing setting only after explicit authorization, or remain blocked. Health-only canary must be a separate data-less/network-disabled container and proves only image liveness. Ordinary startup writes `.tasks.json`, starts download/retry and MP4 recovery workers, may clean temp/orphan files, and may refresh proxies.

For a later approved data transition, add an image-only override after all current Compose files and target only `missav-dlp-web` with `--no-deps --pull never --no-build`; immediately re-render and compare all non-image settings. Compose will stop/recreate the existing service; `--no-recreate` leaves the old image in place. An alternate rename/side-by-side plan has not been validated against the fixed name, project labels, and port; user must decide whether to accept a new container ID or separately approve another tested cutover plan. Rollback must stop the new container, compare against backup, preserve new output/parts, and restore only after proving no conflicting post-start work; never unpack over `/work` wholesale. Recreate the old image by its exact ID and current Compose configuration; Writer remains untouched.

LIMITED_VERIFICATION: `git diff --check` passed for the approval record; synthetic tar archive/restore round-trip preserved state files, synthetic fragment, file mode and symlink. Existing final-image build and offline regression PASS were reused, not rerun.
OPERATIONS: NONE. No production data, container, image, Compose, Writer, DB, NAS/Jellyfin, or Stage11 resource changed.
PLAN_ARTIFACT: `/tmp/dldws001-ops-plan-20261020/deployment-plan.md`; sanitized evidence: `/tmp/dldws001-ops-plan-20261020/evidence/read-only-preflight.json`.

NEXT_DECISION: Select/approve an independent persistent backup target and decide whether losing the old container ID on Compose recreation is acceptable; only after those blockers are resolved request a separate actual-backup execution.

## SEPARATE APPROVED EXECUTION — Synology NAS backup target read-only verification and future container-ID decision

APPROVAL_DATE: 2026-10-20
AUTHORIZATION: Explicit user approval in the DLDWS-001 Synology NAS backup target verification and future container-ID decision request.
EXECUTION_STATUS: BLOCKED; no NAS target could be verified from CT108 and no Proxmox host inspection path was identified.
SHARED_TASK: DLDWS-001
REQUIRED_WORKSTREAMS: downloader,discovery-writer-safety
WORKSTREAM_STATUS: IN_PROGRESS
EXECUTION_CONTRACT_VERSION: 1.0.0
CANONICAL_BASE: teddy-subtitle-stage11 at c738ef22ec3b888dbde9bcdf07e1caef2dbff7cd.
CONTAINER_ID_CHANGE: APPROVED_FOR_FUTURE_APPROVED_COMPOSE_DEPLOYMENT_ONLY; this is not authorization to replace a container now.

This separate phase records the user's decision that Synology is the preferred future Downloader backup destination and that a later separately approved Compose deployment may replace the existing Downloader container ID. NAS target inspection is a Downloader backup prerequisite; the Discovery Writer Safety copy records the shared task authorization and does not authorize Writer, socket, or systemd changes.

### AUTHORIZED_SCOPE

- After exact canonical approval readback in both workstreams, perform read-only inspection of existing NAS mounts visible in CT108; if none is visible there, read-only inspection of existing NAS mounts on an accessible Proxmox host is allowed.
- Identify an actual Synology mount and existing shared-folder path from mount metadata, including mount path, filesystem type, NAS/export identity, mount options, and permission metadata. Do not assume an arbitrary directory is a NAS share.
- Compare the candidate filesystem/source with /opt/missav-dlp-web/work to establish whether storage is independent.
- Read actual free space and, where exactly supported, free inode count. Require at least 40 GB free and 20,000 free inodes. If exact capacity, inode, persistence, independence, or access metadata is unavailable, report UNKNOWN and do not infer PASS.
- Inspect only existing mount and directory metadata. Do not enumerate or read NAS file contents, create a directory, or perform a write test.
- Record the measured result in both ACTIVE_WORK files and the canonical handoff. Reuse the prior production plan and image evidence; do not repeat completed build or regression work.

### PROHIBITED_SCOPE

- No NAS mount/unmount or share configuration change; no directory creation, file write, backup, restore, or cleanup.
- No Downloader container start, stop, restart, replacement, rename, or removal; no Docker build, image change, or Compose edit.
- No download, retry, recovery, MP4 operation, operational database write, Writer service/socket/systemd change, Stage11, NAS/Jellyfin data change, or modification of protected candidate worktrees.
- The future container-ID decision does not waive the independent-backup, restore-verification, pinned-image, data-preservation, or rollback requirements and does not authorize current deployment.

### ACCEPTANCE_CRITERIA

- Confirm the approval record has matching task ID, status, contract version, and required workstreams in both copies and read it back from the exact canonical commit before NAS inspection.
- Report NAS_ACCESS, BACKUP_TARGET, measured free space and free inodes or UNKNOWN, STORAGE_INDEPENDENCE, one recommended existing-share backup path, and any remaining blockers.
- Preserve all prior DLDWS-001 results and the current production state. Record PRODUCTION_BACKUP=NOT_RUN and PRODUCTION_DEPLOYMENT=NOT_RUN.
- If an eligible share is found, stop after recommending it. Actual backup and restore verification require a separate explicit execution approval.

NEXT_DECISION: Complete the authorized read-only NAS mount and capacity inspection, publish the factual result in both workstream records and the canonical handoff, then stop before any backup or deployment.

### EXECUTION_RESULT — Synology NAS read-only target check (2026-10-20)

NAS_ACCESS: UNKNOWN. No NFS, NFS4, CIFS, or SMB3 mount or remote source was visible in CT108. The current LXC environment exposes no Proxmox management tools, configured SSH host alias, or Proxmox hostname mapping; no remote host connection was attempted.
BACKUP_TARGET: BLOCKED. No existing Synology share or eligible backup directory could be identified. No directory was created and no write test was performed.
FREE_SPACE: UNKNOWN for NAS. For comparison only, /opt/missav-dlp-web/work and /var/backups resolve to the same local /dev/loop4 ext4 filesystem; the latest read-only measurement showed 31,988,432,896 bytes available, below the 40 GB requirement.
FREE_INODES: UNKNOWN for NAS. The same local source filesystem showed 6,128,302 free inodes; this is not a NAS target measurement.
STORAGE_INDEPENDENCE: UNKNOWN. No NAS filesystem was visible to compare with the source; /var/backups is on the same filesystem as the source and is not an eligible destination.
CONTAINER_ID_CHANGE: APPROVED_FOR_FUTURE_DEPLOYMENT only. No container operation was performed.
PRODUCTION_BACKUP: NOT_RUN. PRODUCTION_DEPLOYMENT: NOT_RUN. OPERATIONS: NONE.

NEXT_DECISION: Provide an authorized read-only Proxmox host access path or identify an existing Synology share already visible to CT108; then repeat only the read-only mount, capacity, inode, and independence checks. Any new mount requires separate authorization.

## SEPARATE APPROVED EXECUTION — Proxmox Data_5TB production backup and restore verification

APPROVAL_DATE: 2026-10-20
AUTHORIZATION: Explicit user approval in the DLDWS-001 Proxmox 5TB HDD actual backup and restore verification request.
EXECUTION_STATUS: BLOCKED_HOST_ACCESS; no production backup, archive verification, or restore command was run.
SHARED_TASK: DLDWS-001
REQUIRED_WORKSTREAMS: downloader,discovery-writer-safety
WORKSTREAM_STATUS: IN_PROGRESS
EXECUTION_CONTRACT_VERSION: 1.0.0
CANONICAL_BASE: teddy-subtitle-stage11 at f116284f90aa920f56fbb4abda7d3ab00e00b37b.

The approved execution is limited to creating and verifying a backup of the Downloader work data on the separately attached Proxmox Data_5TB disk, then restoring it into a new temporary validation directory on that disk. The paired Discovery Writer Safety record documents the shared DLDWS-001 authorization only; it does not authorize Writer, socket, or systemd changes.

### USER_PROVIDED_TARGETS — NOT REVERIFIED

- Source: Data_2TB, /dev/nvme1n1p1, /mnt/pve/Data_2TB; CT108 path /opt/missav-dlp-web/work.
- Destination: Data_5TB, /dev/sda1, ext4, /mnt/pve/Data_5TB, under /mnt/pve/Data_5TB/dldws001-backups/.
- The stated approximately 2.9 TB free space and 151,919,155 free inodes are user-provided prior observations, not measurements from this execution.
- The only permitted execution host is the actual Proxmox host pve. Downloader LXC is not a substitute. Do not guess an SSH target or alter/mount storage.

### AUTHORIZED_SCOPE

- Only from a confirmed pve host, perform the read-only preflight for CT108 identity, existing Docker container state, source stability, source and destination mounts/devices, free space/inodes, and backup-stream error propagation.
- If every preflight passes, create one uniquely named root-owned mode-0700 backup run directory without overwriting existing files. Read source data through pct exec 108 or another verified read-only method; write only the approved backup and exact-run verification files under Data_5TB.
- Preserve paths, contents, numeric ownership, permissions, available ACL/xattr and sparse-file metadata, and symlink identity without permitting archive path traversal. Capture pipeline errors, use a partial filename until success, and do not auto-retry or force-clean on failure.
- Compare source state before and after, verify archive SHA-256, and restore the archive only to a new empty scratch directory in the same run area. Verify restored file contents, paths, counts, sizes, ownership/modes, and metadata.
- Keep the verified archive. Remove only a verification directory created by this exact run if safe and needed; never remove any pre-existing file.
- Record the final result in both ACTIVE_WORK files and the canonical handoff. Production restore and deployment remain unauthorized.

### PROHIBITED_SCOPE

- Do not run any backup or storage command from Downloader LXC or an unverified host. If the active host is not pve or access is unavailable, stop with BLOCKED_HOST_ACCESS.
- No production container start, stop, restart, recreation, replacement, image or Compose change; no restore into the operational path.
- No changes to source data, Docker/Compose, Writer/systemd/socket, DB, downloads/retries/MP4, NAS/Jellyfin, Stage11, other VM/LXC, or protected candidates.
- No mount/unmount, LXC shutdown, system service interruption, automatic retry, overwrite, or cleanup outside the exact new verification directory.
- Never publish task/settings contents, URLs, tokens, identifiers, or full source listings to GitHub or logs.

### ACCEPTANCE_CRITERIA

- The identical approval scope is present in both active workstreams and read back from the exact canonical commit before any operation.
- PASS requires a stable source, a verified separate Data_5TB device with at least 40 GB and 20,000 free inodes, complete archive integrity, and a real restore comparison.
- If host identity, source stability, device separation, metadata preservation, streaming errors, archive verification, or restore comparison is unknown or fails, stop without asserting backup readiness.
- Report BACKUP_TARGET, SOURCE_STABILITY, PRODUCTION_BACKUP, ARCHIVE_INTEGRITY, RESTORE_VERIFICATION, DATA_PRESERVATION, and PRODUCTION_DEPLOYMENT separately.

### EXECUTION_RESULT — host access preflight (2026-10-20)

CANONICAL_BASE_CONFIRMED: f116284f90aa920f56fbb4abda7d3ab00e00b37b.
CURRENT_EXECUTION_HOST: hostname downloader; systemd-detect-virt reports lxc; root filesystem is /dev/loop4 ext4. This is not Proxmox host pve.
PVE_ACCESS: NOT_AVAILABLE_IN_CURRENT_CONTEXT. No pct or pvesh command, configured SSH host alias, or Proxmox hostname mapping is present. No remote connection was attempted and no storage path was accessed.
SOURCE_STABILITY: UNKNOWN. The production container status and source write activity were not inspected from this non-pve context.
BACKUP_TARGET: BLOCKED. Data_5TB mount, device, available space, free inodes, and separation from Data_2TB were not verified.
PRODUCTION_BACKUP: NOT_RUN.
ARCHIVE_INTEGRITY: NOT_RUN.
RESTORE_VERIFICATION: NOT_RUN.
DATA_PRESERVATION: UNKNOWN. No operational source or destination data was accessed.
PRODUCTION_DEPLOYMENT: NOT_RUN.
OPERATIONS: NONE. No container, storage, source data, service, or deployment resource was changed.

NEXT_DECISION: Rerun this approved backup-only phase from an authorized shell on the actual Proxmox host pve; first repeat every read-only preflight. Do not resume from Downloader LXC or guess a host route.

## SEPARATE APPROVED EXECUTION — production Compose reproduction and rollback readiness

APPROVAL_DATE: 2026-10-20
AUTHORIZATION: Explicit user approval in the DLDWS-001 production Compose reproduction and final rollback readiness request.
EXECUTION_STATUS: COMPLETED_READ_ONLY; configuration reproduction and rollback procedure PASS. Production deployment remains unauthorized.
SHARED_TASK: DLDWS-001
REQUIRED_WORKSTREAMS: downloader,discovery-writer-safety
EXECUTION_CONTRACT_VERSION: 1.0.0
CANONICAL_BASE: 1cc201361471de85769e008e9faf7c3ad83da010.

### APPROVED_SCOPE_AND_ACCEPTANCE

- After identical canonical approval readback, inspect the actual Downloader LXC container, the three existing Compose files in their original order, interpolation sources, local pinned images, and relevant configuration metadata.
- Resolve Compose using sensitive values only in memory; never print or persist inspect environments, full resolved configuration, credentials, URLs, or secret values. Do not assume the Downloader container contains every interpolation input.
- Validate a final image-only override for new image sha256:83322ee82e736b5ba026b8d98d5709b9685ca9c6b051c2a7f4c7b9bf8d058573 and rollback image sha256:da1e46073bb94b1f942b67b2fead20cc00656922b65f446ef7316b48d706aa0f. Compare all other service/project settings and effective container values.
- Verify a reproducible configuration source and recovery route for the /tmp Compose override. Prepare isolated verification material and exact future deployment/rollback commands targeting only missav-dlp-web with no dependency recreation.
- No container lifecycle command, image/tag/build/pull change, operational Compose/env write, data restore/write, download/retry/MP4 operation, Writer/Gluetun change, NAS/Jellyfin/Stage11 change, or protected-worktree modification is authorized.
- Preserve history. Record results in both ACTIVE_WORK files and the existing handoff. Successful configuration validation does not authorize deployment or establish full application health.

### USER_SUBMITTED_BACKUP_EVIDENCE

DATA_BACKUP: PASS, based solely on the user's submitted Proxmox host execution results, not a Codex host verification.
BACKUP_PATH: /mnt/pve/Data_5TB/dldws001-backups/backup-20261020-110732-TbdQOd.
Reported results: BACKUP_ARCHIVE PASS; ARCHIVE_SAFETY PASS; RESTORE_CONTENT_HASHES 8640/8640; SOURCE_RECHECK PASS; RESTORE_METADATA PASS; CONFIG_BACKUP PASS; CONFIG_RESTORE PASS.
SOURCE_MANIFEST_SHA256: 252491423da01d4f1eeabad3e7caeaeac3e8cb23b2eb46818aba91b7be178d16.
Do not repeat these completed backup/restore tests. Reconfirm source/backup state immediately before any later approved deployment.

NEXT_DECISION: Complete only the read-only Compose/interpolation/image-only override and rollback validation; actual deployment requires separate approval. Ordinary startup can save task state, start retry/MP4 recovery workers, clean temporary files, and refresh proxies; health-only READY does not verify production data or application integration.

### EXECUTION_RESULT — read-only Compose reproduction and rollback readiness (2026-10-20)

CANONICAL_APPROVAL_READBACK: PASS at ed9b8596bfcd03e0f6f60e9a2312fd88674139f1; both approval sections matched.
COMPOSE_REPRODUCTION: PASS. Original project/service and all three Compose inputs match the existing container. All file hashes match the prior audit.
ENV_INTERPOLATION: PASS. The actual recorded interpolation source is --env-file /opt/missav-dlp-web/gluetun.env. It resolves without ambient interpolation values; all 31 service environment values and the full effective old/new-image environment match inspect. No secret values were printed or persisted.
IMAGE_ONLY_OVERRIDE: PASS. Both candidate and rollback full models differ from the original only at services.missav-dlp-web.image; exact local image IDs are present. Ports, 14 mounts, Writer RO socket/GID 988, network/DNS, restart, resource/security and execution defaults match.
OLD_IMAGE_ROLLBACK: READY. Explicit env-file, project, original file order, exact old image override and service-only --no-deps --pull never --no-build argument array are validated, not executed.
DATA_BACKUP: PASS solely from the user's submitted Proxmox execution results; not a Codex host verification. The reported 8640/8640 restore hashes and config restore PASS were reused without repeating backup tests.
ROLLBACK_READINESS: READY for configuration and procedure; source/backup/task/parts/queue state and maintenance conditions must be reconfirmed immediately before any separately approved ordinary start.
TEMP_OVERRIDE_RECOVERY: PASS. Exact non-secret contents and SHA-256 880cfcc3a249898091e5589470f7d4f36d1f0893501a7b5dbf374903575c0a94 are preserved in canonical handoff. Isolated reconstruction matched; no production restore ran.
FINAL_VERIFICATION: PASS, 36 checks. The initial helper result is retained: unordered inspect Mounts and an empty dependency label caused false comparisons. The final helper compares complete sorted mount sets and actual Compose dependency semantics; no product behavior or safety check was relaxed.
PRODUCTION_DEPLOYMENT: NOT_RUN. Container 880cf97a6a3dece8e5ea51def22900c3aa41c32c2b73ba8f098c3025d7e9d4ca remained exited (137). Compose/env inputs, Writer PID/socket metadata and Gluetun ID/PID/start state were unchanged. No work data, database, NAS/Jellyfin or Stage11 resource was accessed or changed.
PLAN: /tmp/dldws001-compose-final-20261020-r1zmpp5n/execution-plan.md; SHA-256 0dc8c5189abcf1a300915ba9756e87d171c74b1fb8623e44765d542a3b0a63be.
FINAL_EVIDENCE: /tmp/dldws001-compose-final-20261020-r1zmpp5n/verification-final.json; SHA-256 a6abebb5d123db6ca464f9105962c17268dbef68e8a4d5fab45e2e9c9148e866.

NEXT_DECISION: User decision on production deployment of exact image sha256:83322ee82e736b5ba026b8d98d5709b9685ca9c6b051c2a7f4c7b9bf8d058573 under the recorded backup/rollback and fresh pre-start gates. No execution is authorized by this review result.

## SEPARATE APPROVED EXECUTION — one-time Downloader production deployment and conditional rollback

APPROVAL_DATE: 2026-10-20
AUTHORIZATION: Explicit final user approval in the DLDWS-001 one-time Downloader production deployment and safe rollback request.
EXECUTION_STATUS: COMPLETED_PASS; user-approved concurrency=4 preserved and same-container continuation verified.
SHARED_TASK: DLDWS-001
REQUIRED_WORKSTREAMS: downloader,discovery-writer-safety
EXECUTION_CONTRACT_VERSION: 1.0.0
CANONICAL_BASE: 48d511e0555062c8cc9a737a3cb5d182f209dae3.
ATTEMPT_LIMITS: One candidate deployment; at most one conditional old-image rollback; no automatic retry.
NEW_IMAGE_ID: sha256:83322ee82e736b5ba026b8d98d5709b9685ca9c6b051c2a7f4c7b9bf8d058573.
OLD_IMAGE_ID: sha256:da1e46073bb94b1f942b67b2fead20cc00656922b65f446ef7316b48d706aa0f.

### AUTHORIZED_SCOPE_AND_MANDATORY_GATES

- Publish identical approval scope in both workstreams and verify exact canonical readback before operational preflight or change.
- Reuse the verified execution plan (SHA-256 0dc8c5189abcf1a300915ba9756e87d171c74b1fb8623e44765d542a3b0a63be) and evidence (SHA-256 a6abebb5d123db6ca464f9105962c17268dbef68e8a4d5fab45e2e9c9148e866) in /tmp/dldws001-compose-final-20261020-r1zmpp5n.
- Reconfirm backup disk, archive and source-manifest availability on pve immediately before deployment. The existing successful backup/restore evidence is user-submitted, not Codex-executed. If pve is inaccessible, require fresh user read-only evidence; absent or insufficient evidence blocks as BLOCKED_BACKUP_PREFLIGHT.
- Backup run: /mnt/pve/Data_5TB/dldws001-backups/backup-20261020-110732-TbdQOd; source-manifest SHA-256 252491423da01d4f1eeabad3e7caeaeac3e8cb23b2eb46818aba91b7be178d16. Preserve the archive and prior evidence; do not repeat backup or restore.
- Reconfirm correct CT108/Downloader environment, old container ID/image and exited status, no duplicate/source-writing process or conflicting restart automation, Writer/socket and Gluetun stability, and unchanged ports/mounts/network.
- Read-only recheck tasks and fragments. Block ordinary start on running/pending work, error retries below cap, changed/unknown partial files, orphan/loose temporary files, queued MP4 recovery, damaged source or unexplained backup differences.
- Re-render the exact three-file Compose order with --env-file /opt/missav-dlp-web/gluetun.env, project/service missav-dlp-web, then apply only the validated final image override. Confirm all 31 environment values, 14 mounts, port 58000:5000, Writer RO/GID 988, dependency, network/DNS, security/resources and restart settings. Any drift blocks.
- After every gate passes, execute the single validated candidate command targeting only missav-dlp-web with --no-deps --pull never --no-build. Container ID replacement is approved. No image pull/build/tag change or dependency recreation.
- Inspect actual image/config/restarts, HTTP and application job state, fragment preservation, unexpected download/retry/MP4 activity, read-only Writer application integration and startup logs. Distinguish task serialization from semantic damage; health-only/socket READY alone is insufficient.
- On a critical post-start failure, safely stop only the new Downloader to prevent repeated startup. A single old-image override rollback is allowed only when backup access, old image/config, understood compatible state and no conflicting new data are established. Unknown/conflicting changes block as BLOCKED_MANUAL_RECOVERY; never automatically unpack over production data.
- Preserve source data, backup, old image/config and all prior records. Record the final result in both ACTIVE_WORK files and canonical handoff with remote readback.

### PROHIBITED_SCOPE

No download/retry/recovery trigger, forced job resume, real MP4/NAS transfer test, database direct write, fragment/task deletion, backup modification, Writer/systemd/socket change, Gluetun or other container change, NAS/Jellyfin/Stage11 change, protected candidate edit, image build/pull/retag/delete, repeated deployment/rollback or unrelated product/code change.

NEXT_DECISION: Approved execution completed; see FINAL EXECUTION RESULT and FINAL_NEXT_DECISION below. Real download/MP4 tests remain NOT_RUN.

### USER CLARIFICATION — intentional max_concurrent change and continuation

The user teddy explicitly confirmed that they changed max_concurrent from 2 to 4 and requested continuation. Preserve 4; do not restore 2. The application log records one non-loopback PUT /api/settings with HTTP 200 at 2026-10-20 04:49:54 UTC. Reversing only that field in memory with the existing serializer reproduces the exact prior settings SHA-256, proving all other saved settings are unchanged. No production setting was rewritten by Codex.

The single Compose deployment had succeeded and the initial HTTP/job/Writer/source checks passed. A later settings-hash checkpoint caused a safety stop before this clarification. The existing candidate container 0ea7bb918b1b8095dabd93c70729c45bd5bbca7f857c788b4199bff32274ed28 is stopped on the approved new image.

CONTINUATION_SCOPE: Under the user's request to continue with the intentional setting, start this exact already-deployed container once after verifying its unchanged identity/config, source and approved max_concurrent=4. This is a single resume of the same object; do not rerun Compose, recreate the container, change an image, restore settings/data, or trigger downloads. Repeat actual read-only post-start validation. The original conditional single rollback authority remains subject to safe-data and no-conflict checks.
DEPLOYMENT_ATTEMPTS_USED: 1 of 1.
RESUME_LIMIT: One necessary start of the same stopped candidate object; no automatic retry.
ROLLBACK_ATTEMPTS_USED: 0 of 1.

### FINAL EXECUTION RESULT — Downloader production deployment (2026-10-20)

PRE_DEPLOY_GATE: PASS.
BACKUP_RECHECK: PASS from fresh user-submitted pve evidence: HOST, DATA_5TB_MOUNT, BACKUP_ARCHIVE_READABLE, SOURCE_MANIFEST_SHA256 and PVE_BACKUP_RECHECK all PASS. Codex did not access pve or perform the host backup/restore. The prior 8640/8640 restoration and configuration checks were reused, not repeated.
COMPOSE_RECHECK: PASS, including 36 original and immediate pre-deploy comparisons. Only the target image changed; all 31 service environment values, 14 mounts, port 58000:5000, Writer RO mount/GID 988, dependency, network/DNS, restart and security/resource settings matched. No secrets were printed or persisted.
PRODUCTION_DEPLOYMENT: PASS. Exactly one service-only Compose up used --no-deps --pull never --no-build. No build, pull, retag, second deployment or dependency recreation.
RUNNING_IMAGE: sha256:83322ee82e736b5ba026b8d98d5709b9685ca9c6b051c2a7f4c7b9bf8d058573.
NEW_CONTAINER: 0ea7bb918b1b8095dabd93c70729c45bd5bbca7f857c788b4199bff32274ed28; running; RestartCount 0. The old exited object 880cf97a6a3dece8e5ea51def22900c3aa41c32c2b73ba8f098c3025d7e9d4ca was replaced as approved. Its exact old image remains local.
CONTINUATION: The initial deployment checks passed, then a settings-hash change caused one precautionary stop. The user teddy confirmed their intentional max_concurrent 2-to-4 change and requested continuation. After identical canonical approval readback at 8db43cd72dca47eb681df9dd76ced4fe59196dbb and all fresh resume gates, the exact same new container was started once at 2026-10-20 04:57:33 UTC. No Compose command, image replacement or data restore was repeated. Same-container resume verification completed PASS at 04:58:10 UTC; final checkpoint PASS at 04:58:37 UTC.
USER_SETTING: max_concurrent=4 preserved. The in-memory reversal of only this field exactly reproduced the old settings bytes/hash, proving no other saved setting changed. Codex did not rewrite settings. Live GET /api/settings confirmed 4, auto_retry=true and auto_retry_max=30. No state-changing HTTP request was observed after the resume.
DOWNLOADER_HTTP: PASS. Host /login and authenticated application / returned HTTP 200; /api/tasks and /api/settings returned HTTP 200; /auth/check returned 204. The read-only maintenance probe used an ephemeral in-memory standard Flask session with existing protected credentials; live authentication guard unchanged, interactive login flow not tested. No app/bootstrap import was executed by the probe.
JOB_STATE_PRESERVED: PASS. All four ENOSPC error tasks and retry counts [30,30,30,30] match persisted/API state. Task bytes and semantic content were unchanged. No pending/running task, retry-eligible error or queued MP4 recovery was present.
FRAGMENTS_PRESERVED: PASS. Four task-linked .parts directories, 8637 files and 16996662891 bytes match full pre-deploy SHA-256 and metadata checks after the resume. This includes 8633 TS fragments and four known filelist.txt metadata files. Ownership/modes, directory metadata and other existing root entries match. No orphan .parts, loose temporary TS, unexpected download/retry/remux process or corresponding activity log was observed. At least 35 seconds of monitoring covered two retry-monitor periods.
WRITER_APP_INTEGRATION: PASS strictly for the installed application UnixSocketDiscoveryWriterClient health path from the deployed container using its actual mount/environment/permissions; protocol_version=1 and status=READY. Downloader HTTP/task functionality was verified separately. Library mutation, discovery catalog workflows and full business integration were not exercised; no preflight_holding or mark_absent request was sent.
RUNTIME_INTEGRITY: PASS; all six final application/bootstrap/entrypoint/MP4/proxy/Writer source hashes match the verified image evidence.
ROLLBACK: NOT_NEEDED; zero rollback attempts. Old image/config/backup references remain preserved. Any later restore must account for the user-approved concurrency=4 rather than blindly overwriting it with the older backup value.
REAL_DOWNLOAD_TEST: NOT_RUN. REAL_MP4_TEST: NOT_RUN. Existing four-error-job recovery and Stage11 subtitle quality are outside this PASS.
OPERATIONAL_CHANGES: Only the Downloader container was recreated once, safely stopped once on the subsequently explained setting change, then the same object resumed once. Existing Compose/env/image files were not edited. Normal startup initialized the empty MP4 queue directory/lock and refreshed the proxy pool; no queue job, fragment loss or task mutation occurred. User teddy's settings write is explicitly preserved. Writer PID/socket metadata, Gluetun ID/PID/start state and all other container identities remained unchanged. Codex issued no DB writes, NAS/Jellyfin actions or Stage11 changes.
REMAINING_WARNING: SpoofDPI startup failed and the successful proxy pool refresh reported failed speed measurement. These existing startup warnings did not prevent HTTP/jobs/Writer health or preservation checks; actual download/network behavior remains unverified. No unapproved fix or network/media test was attempted.
DOCUMENT_VALIDATION_NOTE: The first governance check exposed repeated CONTRACT_VERSION field labels in execution history, including three inherited from earlier canonical phases. Their values all remained 1.0.0. Only those execution annotations were renamed EXECUTION_CONTRACT_VERSION, preserving the single authoritative header, contracts, task IDs, prior evidence and authorization meaning. Validation code and safety assertions were not changed.
EVIDENCE_ROOT: /tmp/dldws001-deploy-gate-20261020-bw5kkspl; restricted local evidence, prior checkpoints/failures retained.
RESUME_RESULT_SHA256: de3a33678055823a451886f80725d6fb9a887db5c16501bd25838c375e25660f (resume-result.json).
FINAL_CHECKPOINT_SHA256: 1afda045ebddb619467d49bbad0728fd50dd98eff2f49d6c9583799142596bab (final-after-user-clarification.json).
FULL_POST_RESUME_SOURCE_EVIDENCE_SHA256: bc81d19498dbf790c24509e833f18d8583bcbc331b8019cd198c2ef98e2e0f36 (resume-source-after.json; filenames represented only by digests).

FINAL_NEXT_DECISION: This approved Downloader production transition phase is complete. A separate read-only investigation of the remaining SpoofDPI startup warning is the next proposed task. No download/recovery/MP4/NAS action is authorized by this result. DLDWS-001 remains registered IN_PROGRESS for separately approved follow-up; Governance remains INACTIVE/NONE and Stage11 S11-WX011 is unchanged.

FINAL_DOCUMENT_CHECKS: PASS; all-workstream structure, shared DLDWS-001 preflight, unchanged S11-WX011 preflight, Governance smoke 21/21 and git diff --check. No router/contract/Stage11/validation-script change.
