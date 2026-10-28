# Discovery Writer Safety workstream — active work

WORKSTREAM: discovery-writer-safety
TASK_ID: DLDLIB-001
STATUS: IN_PROGRESS
CONTRACT_VERSION: 1.0.0
REQUIRES_WORKSTREAMS: governance,downloader,discovery-writer-safety

## CURRENT USER-APPROVED DLDLIB-001 OPERATIONS — 2026-10-28 KST

The user explicitly authorized the bounded Downloader-only production image deployment below. This supersedes the earlier DLDLIB-001 coding-phase prohibition on image build/container replacement/restart only for this exact operation, conditional on every safety gate. Prior coding evidence, DLDWS-001 and backup policies are preserved. Governance coordinates authorization/evidence, Downloader owns the change, and Writer Safety participates only to verify Writer invariance and compatibility.

### APPROVED_SCOPE

- After this approval is validated, committed, fast-forwarded and read back from canonical, read-only recheck actual CT108 host/container identity, image, complete Compose project/service/image/network/environment/mount/privilege/command configuration (never expose secrets), current file SHA and byte equality with the canonical pre-fix file, old-image/config rollback, live downloads/remux/tasks and MP4 journals, startup replay of old failures/GANA, Discovery DB read-only accessibility, Writer socket and shared-lock compatibility, and independent Stage9 scheduling.
- Only when all gates including startup and rollback safety PASS: build a reproducible uniquely tagged single-file image layer based on the verified running image ID, replacing only /app/teddy_library_api.py with the canonical MAX_TITLES=500 version. No docker commit or full-source rebuild. Verify candidate import/constant and unchanged runtime configuration. Preserve the old image and Compose configuration; replace only the actual Downloader Compose service without dependency recreation and preserve command, networks, mounts, secrets, environment and permissions.
- Verify running container, constant 500, authenticated /api/library HTTP 200 with actual count, list count and default ordering, web File Management library display, and unchanged jobs/queue/journal, Writer and Stage9 status. Any rollback requires a safe startup/replay path and preserved current state; stop if unproven. Record outcomes and precise evidence in ACTIVE_WORK and canonical handoff. User-supplied baseline image sha256:9ceedeba292ae50980e6fb143589b7c0e12d1abf8c34d82fa49de8a5a500402f and file SHA-256 7847786d04ac9af4c533f4163633db837954b5d15f9723b53fe68c50f72ed055 are historical until freshly verified.

### PROHIBITED_SCOPE

No product source change beyond already published constant, unrelated service/container recreation, direct patching of running container, Docker commit, forced job/download/Organizer/Stage9 work, Writer socket/service modification, Stage9 timer/service changes, NAS/Jellyfin/Discovery DB/settings writes, task or queue edits/deletion, backup movement/deletion, Stage11 changes or broad refactoring. No build/deploy if any mandatory safety gate is unknown or fails; no unsafe rollback or startup replay workaround. Do not publish secrets.

### ACCEPTANCE_CRITERIA

Approval readback, all governance checks and clean diff PASS before operations; fresh baseline, restart replay and rollback safety PASS before image creation/deployment. Candidate contains only the approved file difference and reads MAX_TITLES=500; real API and authenticated web UI verification are separate outcomes. If UI is unverified, do not claim full completion. Preserve unrelated services/data. Report each gate independently, image IDs and canonical SHA.

### DLDLIB-001 OPERATIONS PREFLIGHT — BLOCKED (2026-10-28 KST)

- GOVERNANCE_DEPLOY_AUTH=PASS: user-approved operations authorization was validated and fast-forwarded at 172c103b3a5216356d77a36b4094ecaa21eaef8a, then exact SHA/tree fetched back before live checks. User-provided facts remain distinguished from these read-only observations.
- IMAGE_BASELINE=PASS for identity and library code: current running container ffc4bef1e013c4e784b96bc219f19f6c5491d22937ad138c378dc0c559d7c3b2, image sha256:9ceedeba292ae50980e6fb143589b7c0e12d1abf8c34d82fa49de8a5a500402f; /app/teddy_library_api.py SHA-256 7847786d04ac9af4c533f4163633db837954b5d15f9723b53fe68c50f72ed055 equals canonical pre-fix bytes. Runtime image command python teddy_bootstrap.py; restart unless-stopped. Canonical fix SHA-256 fd615dafaa3ae91f39daa4653d7f8ebe55a154be032191bcb4390a75451708ee. The current image is locally present.
- CT108 live read-only evidence: /downloads/.tasks.json has five completed entries, SHA-256 27f8d654589a43d9664a132b177fee46f6ac1a88740ef5c8a80c900cb2a447c1; no MP4 queue .json files, but four large legacy MP4 files in the queue directory are preserved. No ffmpeg/yt-dlp/aria2 process was observed. Running _recover reads only .json jobs, and the worker filters completed/error states via mp4_recovery_hold_reason; auto_retry_monitor selects error statuses. These are observations, not a guarantee about the in-memory download queue. /api/tasks returned HTTP 401 without authentication; no authenticated session or introspection of the running in-memory queue was available.
- STARTUP_REPLAY_SAFETY=BLOCKED: although disk state and code support a low-risk hypothesis, current live in-memory task/queue state was not verified or coordinated with admission at cutover, so an accepted/racing job cannot be ruled out. Running code can update tasks on startup if statuses/fields differ and can delete matching .*.part.ts files; a current read found none. Settings have all default keys and version 3, so the examined migration logic would not currently rewrite settings. Do not infer safe restart from five completed disk records or zero JSON journals alone.
- Compose project/service missav-dlp-web uses eight inputs, including two /tmp files; all were readable. Rendering without the original invocation environment failed because TEDDY_LIBRARY_DELETE_DISCOVERY_WRITER_GID was missing and TEDDY_PUBLIC_ORIGIN unset. A read-only render using the actual running container's environment and group 988 succeeded: service image reference and declared environment values match; 14 mount destinations/source paths/modes match; restart policy and image default command agree. This partial comparison is not a preserved/validated full configuration and rollback procedure.
- ROLLBACK_READY=BLOCKED: old image exists, but no durable exact Compose/environment snapshot or verified rollback procedure and no safe restart/admission proof exists. Do not claim readiness based on image existence. Discovery DB read-only immutable connection returned 252 holdings (WAL was zero at inspection); Writer socket connection succeeded; Writer service and both Stage9 timers were active; generic wrapper uses --skip-media. These are point-in-time observations.
- One diagnostic mistakenly attempted to read every queue-directory file as JSON and the Python process was killed while encountering large MP4 files. It was read-only; subsequent bounded inspection did not reread media bytes. Afterward the container remained running with the same ID/start time, task/settings hashes matched the earlier read, and Writer/Stage9 units remained active. The kill cause and any transient memory pressure were not independently established.
- CANDIDATE_IMAGE=NOT_RUN; DEPLOY=BLOCKED; LIBRARY_API=NOT_RUN; WEB_UI=NOT_RUN. No image build, container replacement/restart, NAS/DB/Jellyfin write, forced job, settings edit, Writer/Stage9 change, backup movement/deletion or Stage11 change was performed. No candidate image ID exists.
- Next: obtain a normal authenticated live task view and a safe, coordinated method/evidence to rule out in-memory queued/in-flight work and concurrent admission at restart, and establish an exact durable Compose/environment snapshot and verified rollback plan. Repeat time-sensitive gates immediately before a separately continued deployment. Keep DLDLIB-001 IN_PROGRESS in all three workstreams; never alter queue/task state or bypass authentication to force a pass. Web UI remains unverified.

### EVIDENCE AND NEXT_DECISION

User approval 2026-10-28 KST; canonical pre-authorization base 30fd1fc7129c33c88beb421fc65ada3adbd6e425. The user's earlier running container, five completed tasks, empty MP4 queue, 252 holdings and HTTP 503 are historical observations, not current proof of restart safety. Proceed only after exact canonical authorization readback and fresh gates. Keep Governance, Downloader and Discovery Writer Safety IN_PROGRESS / DLDLIB-001 after this phase; restore original DLDWS-001 paired routes and Governance INACTIVE / NONE only during a later separate closeout following operational/UI verification.


## CURRENT TEMPORARY TASK — DLDLIB-001 (2026-10-28)

### OBJECTIVE

Restore the Downloader web file manager's held-library listing with the user-approved minimum title-bound correction. The user explicitly approved temporarily switching Governance, Downloader and Discovery Writer Safety together from their original routing. DLDWS-001 is preserved, not completed or replaced.

### APPROVED_SCOPE

- Governance participation: temporary routing, approval/evidence records and canonical handoff only. Writer Safety participation: shared-routing consistency and Writer invariance only. Downloader owns the library product change.
- Complete and validate registration before product edits. Change only teddy_library_api.py MAX_TITLES from 250 to 500; if needed, update exactly one existing library smoke file. Prove 252 holdings list successfully and 501 remain blocked under the existing bound policy, using isolated fixtures and the existing related smoke.
- Publish scoped governance and product commits to canonical teddy-subtitle-stage11 by normal fast-forward, with exact remote readback. No contract change or new workstream is authorized or needed.

### PROHIBITED_SCOPE

No Docker image build/container replacement/restart, service/timer or Writer socket change, NAS/Jellyfin/operational DB/settings write, download/recovery execution, backup movement/deletion or policy change, Stage9 implementation/operation change, Stage11 change, refactoring, pagination, caching, authentication change, per-title exceptions, filter bypass, or other product behavior changes. Preserve query sorting/search, NAS inventory/path protection and other budgets, subtitle status, Jellyfin and permanent deletion behavior.

### ACCEPTANCE_CRITERIA

Registration preflight and governance structure PASS before coding; 252-item success and 501-item existing-policy rejection plus existing related library smoke PASS; git diff --check PASS; normal canonical fast-forward and exact remote readback. Code/test PASS is not production recovery. DEPLOY=NOT_RUN in this phase.

### EVIDENCE

- User-submitted CT108 diagnosis: missav-dlp-web, Discovery DB /discovery/teddy-discovery.sqlite3 accessible; jav/present=1 holdings=252; runtime MAX_TITLES=250; GET /api/library HTTP 503. Canonical read-only review confirms _build_items raises above MAX_TITLES and listing maps the exception to 503. These runtime observations were supplied by the user, not measured by this coding phase.
- Exact pre-transition canonical base: a7f90446094f6a703d88e5ebb3d3517a8a4ba2f7. Original router and three ACTIVE_WORK documents are recoverable byte-for-byte by that commit and these blob IDs:
- docs/governance/ACTIVE_WORK.md: Git blob 7791163613b2c647ffc16481c6704319d69b98a1
- docs/governance/governance/ACTIVE_WORK.md: Git blob cf424aeddf51775fb009499e125b8765e4f27f44
- docs/governance/downloader/ACTIVE_WORK.md: Git blob c02d122bbff3ff323f13bcb404caac985c68a40c
- docs/governance/discovery-writer-safety/ACTIVE_WORK.md: Git blob 4403afe868fc6847344d48aa95221880468a8f38
- Original live metadata: Governance INACTIVE / NONE, contract 1.0.1, requires governance; Downloader and Discovery Writer Safety IN_PROGRESS / DLDWS-001, contract 1.0.0, requires downloader,discovery-writer-safety. Stage9 IN_PROGRESS / STG9MEDIA-001 and Stage11 IN_PROGRESS / S11-WX011 remain unchanged.
- All original DLDWS-001 objectives, status/approvals, deployment/recovery evidence, candidates, Writer safeguards and backup preservation policy remain preserved below and at the exact pre-transition commit. Earlier live-task statements below are historical while this temporary task is active.

### DLDLIB-001 IMPLEMENTATION RESULT — 2026-10-28

- GOVERNANCE_REGISTRATION=PASS: registration commit b7f129b029b1a54eb63338633fb500ee69f6e63b was published by normal fast-forward and fetched back with exact SHA/tree equality before product edits.
- LIBRARY_FIX=PASS: the only product-code change is teddy_library_api.py MAX_TITLES 250 -> 500. All other NAS inventory budgets, path validation, listing/search/sort/subtitle/Jellyfin/deletion logic are unchanged.
- TESTS=PASS: the existing teddy_library_api_smoke.py now adds isolated real-SQLite/Flask API fixtures: 252 holdings HTTP 200 with 252 returned items; 501 holdings HTTP 503/library_unavailable before any NAS inventory call; fixture DB bytes unchanged by each request. The 252 test reproduced HTTP 503 before the constant change. Existing library API smoke and teddy_library_ui_smoke.py pass; git diff --check passes.
- Test runtime: system Python 3.13 with existing Flask dependencies from /tmp/dl001-py310-testenv-20261019/lib/python3.10/site-packages on PYTHONPATH; -B disables bytecode writes. Default Python lacked Flask and the old Python 3.10 environment lacked its standard library; no operational environment was installed or modified. All test DB/files/NAS/Jellyfin boundaries were isolated fixtures.
- DEPLOY=NOT_RUN; actual production API/UI recovery remains unverified. Governance, Downloader and Writer Safety stay IN_PROGRESS / DLDLIB-001 with the three-workstream requirement. Stage9 and Stage11 are unchanged; DLDWS-001 and backup preservation history remain intact.
- Next operational gate: obtain separate deployment authorization; freshly verify CT108 current image/source/Compose identity, the reviewed one-line product delta and rollback readiness, current task/queue state and Writer/dependency compatibility. Deploy only the authorized Downloader change, then verify authenticated GET /api/library and the web File Management library against current holdings. Do not force downloads/recovery, mutate NAS/DB/settings, or restore routing until the separately approved deployment/UI verification and closeout are complete.

### NEXT_DECISION

After code/test PASS, KEEP all three routes IN_PROGRESS / DLDLIB-001 with governance,downloader,discovery-writer-safety until a separately approved operational deployment and web UI verification are complete. This phase grants no deployment permission. Only a later explicit closeout restores the exact original Governance INACTIVE / NONE and DLDWS-001 paired routing above; never restore prematurely or discard DLDWS-001 history.


## JOINT DEPLOYMENT PARTICIPATION CLOSED — STG9MEDIA-001 (2026-10-28)

The user approved closing the temporary Stage9 deployment overlay using the submitted CT108 measurements. Governance and Stage9 ACTIVE_WORK record the complete attributed evidence: PPPE-446 scheduled completion, actual NAS MP4 size/NFO (769 bytes)/poster.webp (11,010 bytes), and Jellyfin VISIBLE at 2026-10-28T00:02:20+00:00; SNOS-403 and FNS-258 also have completed sidecars and VISIBLE. The user-submitted timer/--skip-media/success logs support bounded deployment closeout; Codex performed only a read-only canonical create-only/no-overwrite source review, not these operational actions.

Original DLDWS-001 IN_PROGRESS / downloader,discovery-writer-safety routing is restored. Its objective, approval state, candidates, deployment/recovery results, all historical evidence and backup preservation policy remain intact. No backup policy is changed and no cleanup task is registered. Stage9 continues independently as STG9MEDIA-001 / IN_PROGRESS; no full-product completion is claimed. Earlier joint instructions below are historical and grant no renewed joint deployment authority. This closeout makes governance/handoff edits only; no product, Writer socket, Stage11, runtime, NAS, DB, Jellyfin or backup mutation occurs. Next decision: proceed only within the original DLDWS-001 approvals and independently authorized tasks.


## HISTORICAL CLOSED JOINT STAGE9 OPERATIONS PARTICIPATION — 2026-10-27

User-approved `STG9MEDIA-001` temporary participation only to preserve the existing Writer socket lifecycle and shared title locks during the Stage9 scheduled-owner transition. No Writer socket source, test, service, socket, permission, data, or evidence change. Preserve DLDWS-001 history and restore paired routing at closure; exact cutover boundaries are in Governance/Stage9.

**Historical metadata normalization (2026-10-23, DLDWS-001):** Only the five unquoted fields above define the live workstream task. Older approvals and execution evidence below remain in this document; their repeated metadata labels are quoted solely so the unchanged governance validator does not mistake historical declarations for live ones. The exact complete pre-normalization file is preserved byte-for-byte at `docs/governance/discovery-writer-safety/history/DLDWS-001_ACTIVE_WORK_before_field_normalization_ac476f4.md` (Git blob `348c0957a5feb0833dfd1467a07cf9f995e373b8`). Future historical entries must quote metadata lines or express them as prose. This changes no task authorization, safety boundary or execution result.

## TEMPORARY JOINT TASK PARTICIPATION — STG9MEDIA-001 (CLOSED 2026-10-26)

Closed on 2026-10-26 after confirming the integrated Stage9 transition made no Writer socket source, service, socket, or evidence changes. This did not complete or replace DLDWS-001. Its original objective, approved scope, progress, candidate references, and prior evidence remain intact. The live metadata and required workstream set below are restored to `DLDWS-001` / `downloader,discovery-writer-safety`.

## REACTIVATED JOINT PARTICIPATION — STG9MEDIA-001 (CLOSED 2026-10-26)

CLOSED on 2026-10-26 at the NAS least-privilege preflight. No Writer socket source, service, socket, permissions, database, or evidence was changed. DLDWS-001 remains the original task and all its objective, work, progress, candidate references, and evidence are preserved.

- Allowed: read-only confirmation that the generic and dedicated Stage9 execution paths retain the existing Writer lock and do not change the Writer Unix socket lifecycle.
- Prohibited: any Writer socket source, service, socket, permission, database, or evidence change; no DLDWS-001 implementation or test change.
- The joint scope is limited to the one-time Stage9 cutover recorded in Governance ACTIVE_WORK and the Stage9 reactivation record.

## CLOSED SHARED PARTICIPATION — STG9MEDIA-001 (BLOCKED 2026-10-26)

The user approved temporary shared registration for the Stage9 transition. This does not complete, replace, or rewrite DLDWS-001; its objective, progress, candidates, and evidence below remain preserved. Discovery Writer Safety participation is limited to confirming the transition does not alter Writer socket lifecycle, service, permissions, or data.

The one-time joint activation was read back, then the transition stopped before operational changes at the NAS least-privilege access gate. No Writer socket source, service, socket, permission, database, or evidence was changed. Original DLDWS-001 routing is restored.

## CLOSED STG9MEDIA-001 OBJECTIVE

Preserve the DLDWS-001 Writer socket safety boundary during the shared Stage9 transition and confirm no Writer implementation or operation is included.

## CLOSED STG9MEDIA-001 APPROVED_SCOPE

- Read-only review of the shared Stage9 invocation/lock boundaries for Writer socket impact.
- Verify the transition does not modify Writer socket code, service, socket pathname, permissions, lifecycle, or database.
- Preserve the original DLDWS-001 objective, candidate, progress, and evidence byte-for-byte apart from the required live routing metadata and this participation record.

## CLOSED STG9MEDIA-001 PROHIBITED_SCOPE

- No Writer socket source/test changes, service/unit/socket changes, permission changes, cleanup, or database work.
- No change to the DLDWS-001 candidate/evidence or Stage11 work.
- No unrelated Downloader behavior or production service changes.

## CLOSED STG9MEDIA-001 ACCEPTANCE_CRITERIA

- Shared Stage9 changes preserve Writer socket ownership and lifecycle code and do not invoke Writer operations.
- DLDWS-001 history, candidate references, and evidence remain intact; original routing is restored at joint-task closure.

## CLOSED STG9MEDIA-001 EVIDENCE

- User approval received 2026-10-26 KST. Activation base and current remote SHA: `9c89efe29c5b9af7b5cc70aff305738a9723d2c2`.
- No Writer source or operation is authorized by this participation; evidence will be updated only with verification of that boundary.

## CLOSED STG9MEDIA-001 NEXT_DECISION

Continue this shared registration only while the Writer boundary remains unchanged; restore DLDWS-001 routing and its original required-workstream set at closure.

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


## SEPARATE APPROVED EXECUTION — read-only SpoofDPI and proxy-speed warning investigation

APPROVAL_DATE: 2026-10-20
AUTHORIZATION: Explicit user approval to investigate the two remaining production network warnings, without reproduction or repair.
EXECUTION_STATUS: COMPLETED_READ_ONLY; findings and unresolved causes recorded below.
SHARED_TASK: DLDWS-001
REQUIRED_WORKSTREAMS: downloader,discovery-writer-safety
EXECUTION_CONTRACT_VERSION: 1.0.0
CANONICAL_BASE: e7323e553c625163c9ff0eb97d7438713a0cde9f.

### AUTHORIZED_SCOPE

- Read existing relevant Docker logs, deployed source/binary metadata and execution configuration, and current process/listener/network metadata. Reuse prior evidence; do not repeat successful deployment or data-preservation tests.
- Trace SpoofDPI startup conditions, actual failure stage, optional/required role and fallback behavior; distinguish evidence from unverified hypotheses.
- Trace successful proxy-list refresh separately from speed measurement, including actual failure handling, selection fallback, and any proven relationship to SpoofDPI. Report UNKNOWN when logs cannot distinguish timeout, DNS, TLS, authentication or other causes.
- Preserve running image sha256:83322ee82e736b5ba026b8d98d5709b9685ca9c6b051c2a7f4c7b9bf8d058573 and user-approved max_concurrent=4. Preserve prior production deployment/data/Writer PASS and REAL_DOWNLOAD_TEST=NOT_RUN.
- Writer Safety participates only for shared-task authorization consistency; Writer itself is outside this investigation.
- Record sanitized findings identically in both ACTIVE_WORK files and existing canonical handoff, with exact remote readback. Suggest at most one smallest scoped follow-up; apply no fix.

### PROHIBITED_SCOPE

No lifecycle/Compose command, SpoofDPI execution/restart, proxy speed rerun, new external connection test, settings/environment/source edit, image build/pull/replace, actual download/retry/MP4 action, download/DB write, Writer/Gluetun/NAS/Jellyfin/Stage11 change, or protected candidate edit. Do not expose proxy endpoints, credentials, URLs, cookies or tokens. Only these approved records/handoff and isolated sanitized evidence may be written.

### ACCEPTANCE_AND_NEXT_DECISION

Identify exact log/code/config locations and bounded impact for both warnings. Report root cause CONFIRMED/LIKELY/UNKNOWN, relationship CONFIRMED/NOT_ESTABLISHED and download impact BLOCKING/DEGRADED/NO_IMPACT_CONFIRMED/UNKNOWN; preserve uncertainty without an active reproduction. Finish after read-only findings; repairs and real-use tests require separate user approval.

### EXECUTION_RESULT — read-only network warning investigation (2026-10-20)

SPOOFDPI_ROOT_CAUSE: UNKNOWN. The failure stage is confirmed, but the reason for process termination cannot be recovered from the retained output.
PROXY_SPEED_ROOT_CAUSE: CONFIRMED for the warning/selection condition; the underlying individual bandwidth-request exception category remains UNKNOWN.
ERROR_RELATION: NOT_ESTABLISHED.
DOWNLOAD_IMPACT: UNKNOWN for real downloads; static fallback and remaining working proxy inventory do not prove real-use success or a global download block.
PRODUCTION_CONTAINER: UNCHANGED.
DATA_PRESERVATION: NO_WRITES_BY_INVESTIGATION.
PRODUCTION_DEPLOYMENT: NO_NEW_DEPLOYMENT.
REAL_DOWNLOAD_TEST: NOT_RUN.

#### SpoofDPI evidence and bounded impact

- Existing Docker logs contain [System] SpoofDPI 가동 실패 at 2026-10-20T04:46:52.959857000Z and 04:57:35.770829000Z. The deployed app.py:124-142 spawns exactly [spoofdpi], waits two seconds and emits that message only when poll() is not None. This proves child termination by the poll, not a binary-not-found branch. The actual return code, termination signal and child diagnostic are UNKNOWN.
- Binary /usr/local/bin/spoofdpi exists, executable mode 0755, uid/gid 501:50, ELF linux/amd64, SHA-256 73336b61fb2c4439352a19b2e397e956d3318a098cbc339207b5441198de93d0. Static Go build metadata reports github.com/xvzc/spoofdpi v1.5.5+dirty, revision 0b49eafe80fca3636fdf58a338b405f663c9c37d. The binary was read, never executed. The application process UID/GID is 0:0; no current SpoofDPI process or TCP 8080 listener exists. Current port state cannot establish whether there was a startup-time collision. No argument, config, port, network, Docker permission or version incompatibility is proven.
- app.py:128-137 redirects stdout to PIPE and stderr to that same pipe, but never reads/forwards the pipe or records the return code. The deployed teddy_logging capture does not intercept subprocess pipes. Thus the existing generic message cannot identify DNS/TLS/listen/config/permission failure; no reproduction was attempted.
- SpoofDPI is the optional local HTTP proxy leg for custom MissAV HTML extraction, expected on loopback port 8080. Normal startup attempts it regardless of spoofdpi_enabled; health-only suppresses the spawn. The setting controls the extraction proxy preference. app.py:241-258 tries local proxy then None with per-request error handling. Actual deployed teddy_entrypoint.py:389-403 uses that custom extractor. teddy_bootstrap.py wraps task requests with teddy_routing.request_route; teddy_routing.py:40-44 overrides explicit request proxies for selected public-proxy/VPN routes. Generic downloads and proxy-pool initialization do not require the SpoofDPI process. The missing local leg may reduce reachability for sites requiring it, but actual download impact is untested.

#### Proxy measurement evidence and bounded impact

- The two retained refresh-completion logs report 48 candidates -> 12 healthy at 04:47:23 UTC and 48 -> 7 healthy at 04:58:08 UTC, both with the speed warning. They are completion, not pool-initialization-failure logs. A single read-only local GET /api/proxy/status (existing snapshot-only handler) confirmed enabled=true, ready=true, refreshing=false, candidate_count=48, healthy_count=7, speed_tested_count=4, selected current_speed_bps=0 and current_learned_speed_bps=0. last_error is empty; all three feed sources report no error. No endpoint, exit IP, credential or raw error text was retained.
- Therefore four retained proxies have successful bandwidth measurements: this is not total speed-test failure or a failed proxy pool. teddy_proxy_pool.py:375-383 decides the warning only from healthy[0].speed_bps, ignoring the successful measurements of other rows. snapshot():624 counts all positive measurements, explaining the apparent disagreement between the log and live state.
- _measure_bandwidth():251-281 requires HTTP 200 and at least 256 KiB of the requested 512 KiB within timeout=10; it otherwise leaves speed_bps=0 and stores a truncated bandwidth_error on the in-memory row. Possible failures include HTTP status, short body and request exceptions, but no existing evidence identifies which of timeout/connect/DNS/TLS/auth/proxy-format categories occurred for the selected row. snapshot() does not expose bandwidth_error, refresh logs omit it, and _save():107-116 does not persist measurement rows. No measurement was rerun or process memory probed.
- _rank_by_real_speed():318-338 intentionally keeps HTTPS-verified candidates even when benchmarking fails. _selection_key():303-315 substitutes max(1,1000000-latency_ms) when measured/learned speed is unavailable, then applies failure/success weights. It does not prioritize successful measurement as a separate tier. An unmeasured/failed row can therefore precede measured rows, as the current selected zero-speed row and four other positive measurements demonstrate. The log reports the selected row rather than aggregate measurement success.
- ensure_ready():428-448 and current_proxy():546-555 use enabled/healthy inventory, not a positive speed requirement. A benchmark failure does not by itself disable the proxy download path. Actual site accessibility, throughput and correct best-proxy choice remain unverified; ranking behavior was not modified.
- _check_proxy and _measure_bandwidth pass each candidate proxy explicitly, in independent worker threads without a SpoofDPI route context. SpoofDPI uses its separate child/local-listener path. No direct code or retained runtime evidence establishes a common failure cause; shared environmental causes cannot be ruled out.

#### Preservation, next decision and evidence

- Container 0ea7bb918b1b8095dabd93c70729c45bd5bbca7f857c788b4199bff32274ed28 remains running on sha256:83322ee82e736b5ba026b8d98d5709b9685ca9c6b051c2a7f4c7b9bf8d058573, same PID/start timestamp and RestartCount 0. User setting max_concurrent=4 was observed and not changed. Prior deployment, HTTP, job/fragment preservation and Writer-client health PASS remain historical results, not repeated tests in this investigation.
- No lifecycle, SpoofDPI execution, proxy refresh/measurement, external network test, production data/DB write, Writer/Gluetun/NAS/Jellyfin/Stage11 change, or protected-worktree edit occurred. The one local snapshot GET caused no refresh and used an ephemeral in-memory standard Flask session; no app/bootstrap import or secret persistence. Production state/task/parts preservation tests were not rerun.
- ONE_MINIMAL_FOLLOWUP_PROPOSAL: With separate approval, add only the child's return code and bounded, redacted child-output diagnostics to app.py:start_spoofdpi(), so the actual early-exit cause can be identified. Keep startup arguments, routing, proxy selection and normal behavior unchanged. This is a proposal only; no patch, deployment, restart or real-use test is authorized or performed here.
- EVIDENCE_ROOT: /tmp/dldws001-network-warning-audit-20261020-a2i6tx4f (0700; files 0600). findings.json SHA-256: 8b8e0d3a0c2f9916e0b591a024b668c43efa720e70e6a63f845a6a4a23ad4cc1.
- Deployed source SHA-256: app.py 5912b09955493ce74919eb0e017f9e09a842e88ef30c778c9bfeee7b73676287; teddy_proxy_pool.py 9076e7b1ffd94f7868ea3b80aaa3c226233978d8566b7bcc70f7b4c2afcdf41e; teddy_routing.py e1c0c63b4ac360d927873adc5fd5ea6ac4b23743eef4fb55c9d20802932f2254; teddy_bootstrap.py 0bddf29291379fa01b529429303460f85e7c863887d856e99502d5e2e3ae87d4; teddy_entrypoint.py a538f2087ff6466d60ee750551605087932d041ae1667f11951875fb02022916. Sources came from the running container filesystem without import, not assumed from canonical product code.

NEXT_WARNING_DECISION: Read-only investigation complete. The only proposed next action is the separately approved minimal SpoofDPI diagnostic change above; no remediation or real-use test follows automatically.


## SEPARATE APPROVED EXECUTION — isolated Downloader restart/bulk retry UI and SpoofDPI diagnostics

APPROVAL_DATE: 2026-10-20
AUTHORIZATION: Explicit user approval for implementation and isolated tests of the three features listed below.
EXECUTION_STATUS: AUTHORIZED_ISOLATED_IMPLEMENTATION; no production connection or deployment authorized.
SHARED_TASK: DLDWS-001
REQUIRED_WORKSTREAMS: downloader,discovery-writer-safety
EXECUTION_CONTRACT_VERSION: 1.0.0
CANONICAL_BASE: 3a4eed998f99d55433c40b27f1f4715d182e4825.

### AUTHORIZED_SCOPE

- Add a settings-screen button to restart only the Downloader container after explicit confirmation and only when the app can prove no queued/running/paused-transition/MP4 work exists. Require authenticated CSRF-protected requests, fixed target identity, one in-flight operation, and verification of a real post-restart application response before the UI reports success. Reuse existing constrained helper patterns where applicable.
- If no least-privilege controller already exists, implement and test only an isolated host-side control-helper candidate with a fixed Downloader target/protocol. The web app must not receive the Docker socket or arbitrary command/target API. Do not install, grant privileges to, or connect an operational helper. Mark production restart integration BLOCKED_PENDING_APPROVAL until separately approved host wiring exists.
- Add a download-list button and server bulk-retry operation that rechecks current state, includes only failed tasks, avoids duplicate/auto-retry queue races, preserves the existing manual-retry retry-budget reset semantics and all .parts/resume data, reports per-item success/skipped/failure, and fails closed when state or available bytes/inodes are insufficient. Keep max_concurrent=4. Use only synthetic files/tasks in tests; never enqueue or trigger an actual download.
- Add bounded, redacted SpoofDPI early-exit diagnostics in app.py without changing its command arguments, routing, automatic restart behavior, or network behavior.
- Update both source UI and the existing build-time UI patch path so the buttons survive Dockerfile patch ordering. Preserve the existing authenticated UI, individual retry, and settings-save behavior.
- Run focused isolated unit/smoke checks and diff validation. Keep all product changes on an isolated candidate branch and do not push product code or build/deploy Docker images.
- Publish this same authorization and final evidence in both workstreams and canonical handoff. Discovery Writer Safety participates for shared-task authorization only; no Writer code/resource is in scope.

### PROHIBITED_SCOPE

No production Docker or other service lifecycle operation, helper installation/privilege grant, Compose/systemd/host setting change, real download/retry/MP4 task, proxy measurement or external test request, DB/production work-file change, Writer/Gluetun/Selkies/NAS/Jellyfin/Stage11 change, verified image build/deployment, or product-code push to canonical. Do not alter max_concurrent=4 or the existing four failed tasks and 8,637 fragments. Do not implement broader proxy routing or automatic SpoofDPI recovery.

### ACCEPTANCE_AND_NEXT_DECISION

Focused tests cover restart authentication/CSRF/fixed target/activity gates/single-flight/readiness semantics; bulk state eligibility/duplicates/auto-retry race/ENOSPC/partial outcomes/fragment preservation/individual retry regression; SpoofDPI normal/early exit/missing executable/redaction/output bounds; and final patched UI presence/responsive behavior. Any unavailable browser or operational integration evidence stays UNKNOWN/BLOCKED rather than being inferred. Report implementation and test results separately from operational availability. A separately approved host-helper integration and production deployment are future decisions.


## SEPARATE APPROVED EXECUTION — Downloader restart helper installation and safe connection

APPROVAL_DATE: 2026-10-20
AUTHORIZATION: Explicit user approval in the DLDWS-001 Downloader restart helper installation request.
EXECUTION_STATUS: AUTHORIZED; operational preflight pending; no helper files or services installed.
SHARED_TASK: DLDWS-001
REQUIRED_WORKSTREAMS: downloader,discovery-writer-safety
EXECUTION_CONTRACT_VERSION: 1.0.0
CANONICAL_BASE: 37cb16030930f7fe7edd7c8fa9423b4e0f90e9dc.

### AUTHORIZED_SCOPE

- Reuse the existing isolated helper candidate at /tmp/dldws001-ui-convenience-20261020 without changing its dirty worktree; verify the exact execution environment and Docker-engine boundary before any installation.
- Install only a Downloader-specific helper and minimum required settings on the verified Downloader Docker-engine host, and connect only a restricted local client path if this can be done without recreating or changing the production Downloader container.
- Enforce a fixed missav-dlp-web target, authenticated/restricted local communication, no arbitrary command or target input, no Docker socket exposure to the web application, and read-only identity/status checks.
- Validate synthetic requests and use a mock backend for any restart-shaped test. Never invoke a real Docker restart.
- Reassess active, queued, pause-transition, MP4/recovery, and auto-retry state at the execution boundary. If the existing guard cannot guarantee no work starts between the app check and helper execution, keep the restart operation unavailable and report BLOCKED_SAFETY_GAP.
- Record sanitized results in both affected ACTIVE_WORK files and the canonical handoff, then verify exact remote readback. Discovery Writer Safety participates for shared-task consistency; no Writer resource is in scope.

### PROHIBITED_SCOPE

No docker restart, compose lifecycle command, production container stop/start/recreate/replace, image build/pull/deployment, real download/retry/MP4 work, task or fragment change, Writer/Gluetun/Selkies/NAS/Jellyfin/Stage11 change, Docker socket exposure to the web app, or product-code publication. If connection requires changing Compose, image, mount, or the existing container, stop without making that change. If installation fails, only resources created by this execution may be disabled or removed.

### ACCEPTANCE_AND_NEXT_DECISION

- Confirm the target is the Downloader LXC/host with the Docker engine; do not infer CT identity or install on the Proxmox host.
- Verify helper ownership, permissions, fixed target, caller restriction, duplicate/replay behavior, read-only status, client connectivity, and mock-backend behavior without changing the production container.
- Do not leave a real restart interface enabled unless the no-work condition is guaranteed through the actual execution point. Otherwise report RESTART_RACE_SAFETY=BLOCKED and keep restart unavailable.
- Report installation/connectivity separately from production UI deployment and real restart; the latter remain NOT_RUN/NOT_DEPLOYED.


### EXECUTION_RESULT — Downloader restart helper preflight (2026-10-20)

HELPER_INSTALL: BLOCKED. No helper file, service, socket, or production setting was installed or changed.
HELPER_AUTH: FAIL for production readiness. The candidate checks only SO_PEERCRED uid==0 with a root:root 0600 socket; it does not bind callers to the Downloader container identity. Its duplicate/replay registry is in-memory and is reset on helper restart/eviction. The synthetic non-root rejection passed, but operational peer mapping and caller isolation were not verified.
FIXED_TARGET_CONTROL: PASS for isolated mock only. The protocol rejects an extra target field, hard-codes missav-dlp-web, checks the Compose service label, and the mock asserted the exact inspect/restart argv. It does not pin the expected container ID or image; no operational container identity was read.
RESTART_RACE_SAFETY: BLOCKED. The UI route candidate performs its no-work check under queue_admission_lock and sets downloader_restart_pending, and supported queue admission paths check that flag. However, the host helper itself has no one-time app-issued permit/state recheck and accepts a restart from any peer that passes uid==0; execution-time safety and the deployed path were not established. Do not enable the restart operation.
HELPER_CLIENT_CONNECTIVITY: BLOCKED. Runtime was hostname downloader and virtualization type LXC, but CT108 identity was not independently confirmed. /usr/bin/docker exists; Docker API access returned permission denied even as uid 0, so read-only inspect of missav-dlp-web and its mounts could not run. systemctl could not access the system bus. Static systemd verification was blocked by “SO_PASSCRED failed: Operation not permitted”.
REAL_RESTART: NOT_RUN.
RESTART_UI_PRODUCTION: NOT_DEPLOYED.
BULK_RETRY_PRODUCTION: NOT_DEPLOYED.
PRODUCTION_CONTAINER: UNCHANGED; no lifecycle command succeeded or was issued.
PRODUCTION_DEPLOYMENT: NOT_RUN.

CANONICAL_APPROVAL_READBACK: PASS at 26b35a4ef48d283a37343617921dff8e079b3f72; the approval entry is identical in both workstreams. The local checkout is branch codex-stage11-wx001-20261014 at 761fcdce563b32edfa31f5f44f09eb11535e9d8f, not the canonical branch; GitHub connector readback was used for canonical state.
CANDIDATE: /tmp/dldws001-ui-convenience-20261020, branch codex/dldws001-ui-convenience-20261020, HEAD 37cb16030930f7fe7edd7c8fa9423b4e0f90e9dc. Its dirty changes were preserved. Helper SHA-256 a2699e7dd512f73d44c9fa49a8ca7014a2cf277a593cc5a1059ce63135c54776; smoke SHA-256 0c33cfcf4eb8f415bef2c98e0bc8cbdb3ef3c205c3616b3570bff720084b25e7; socket unit SHA-256 055520d6b49c0db7b8506833cbed3d7e43cf39eb01c084eff1474f84096b162b; service unit SHA-256 f8131bed81acff2257179bafef495e64bb84fd07686ee32c411258a222b5cf67.
VALIDATION: Existing candidate mock-backend control smoke passed; it did not contact Docker or a socket. No production status/data, Writer, Gluetun, download, image, Compose, or Stage11 resource was changed. Remote outcome record readback follows in this execution.
NEXT: Close the helper caller-identity/replay and execution-time permit gaps, then repeat preflight from a verified CT108 session with Docker/systemd access. Do not enable a live restart endpoint before both gates pass.

## SEPARATE APPROVED EXECUTION — Downloader server restart excluded (2026-10-20)

USER DECISION: Exclude the new Downloader server restart feature from this isolated candidate. This scope reduction supersedes the prior helper-install approval. Preserve the earlier approval and blocked helper preflight as historical records; do not infer helper installation or restart authorization from them.

SERVER_RESTART_FEATURE=EXCLUDED
HELPER_INSTALL=NOT_RUN
BULK_RETRY=PASS
FLASK_ROUTE_INTEGRATION=PASS
ENOSPC_INODE_BLOCKS=PASS
PARTS_PRESERVATION=PASS
SPOOFDPI_DIAGNOSTIC=PASS
UI_BROWSER=PASS
DESKTOP_LAYOUT=PASS (1440x900)
MOBILE_LAYOUT=PASS (390x844)
SELKIES_SETTINGS_INDIVIDUAL_RETRY=PASS
FINAL_DOCKERFILE_UI_PATCH=PASS
DOWNLOADER_RESTART_CODE_REMAINS=NO
PRODUCTION_DEPLOYMENT=NOT_RUN
REAL_DOWNLOAD_TEST=NOT_RUN
OPERATING_RESOURCES_CHANGED=NONE

The candidate at `/tmp/dldws001-ui-convenience-20261020`, branch `codex/dldws001-ui-convenience-20261020`, HEAD `37cb16030930f7fe7edd7c8fa9423b4e0f90e9dc`, was edited in place without reset, clean, rebase, or commit. Removed the Downloader-only settings button/client handler/API routes, restart-pending flag and its queue gates, helper transport code, helper smoke cases, Docker helper units/service/socket, helper-only ignore entry, and restart-only styling/build markers. The shared `queue_admission_lock` remains around download admission, automatic retry, manual retry, and bulk retry; existing Selkies restart controls remain. The settings copy still says changes require a restart.

Focused validation used an isolated synthetic filesystem/app and no production jobs. The actual Flask test_client covered bulk-route auth/CSRF, failed-only selection, already-queued and MP4 exclusions, duplicate protection against the automatic retry lock race, byte/inode fail-closed behavior, partial results, retry state, and synthetic fragment hashes. Synthetic admin smoke retained SpoofDPI early-exit diagnostics and bulk retry checks. The Dockerfile UI patch was replayed in `/tmp/dldws001-ui-restart-excluded-20261020`; the resulting UI retained the bulk button, Selkies controls and settings guidance, and had no Downloader restart button or request handler. Node.js v24.22.0 and Chromium 156.0.8078.4 ran 10 synthetic browser scenarios. Unexpected console errors: 0; external/production requests: 0. Browser result: `/tmp/dldws001-ui-restart-excluded-20261020/evidence/browser-results.json`, SHA-256 `8241077e96b880a29e425a7fb6a22283d5cbb9ce65c788d724d48bf2d1ea0fa6`. Python syntax and `git diff --check` passed.

Helper installation, live restart, Docker build/deploy, production download/retry, and canonical product-code merge were not run. The existing 4 production error jobs, 8,637 fragments, `max_concurrent=4`, Writer/Gluetun, NAS/Jellyfin and Stage11 remain outside this execution and unchanged.

NEXT: Decide separately whether to authorize canonical publication of the remaining bulk-retry and SpoofDPI candidate changes; no helper installation or production deployment follows automatically.


## SEPARATE APPROVED EXECUTION — Publish bulk retry and SpoofDPI (2026-10-20)

USER_APPROVAL: The user explicitly approved publishing only the verified failed-download bulk retry UI/API and SpoofDPI early-exit diagnostics to the canonical branch. This approval supersedes the earlier prohibition on canonical product-code publication for these two functions only.
CANONICAL_BASE: fd22b55e4ec2fd1bd4846c852d7b3577e97b2544
CANDIDATE: /tmp/dldws001-ui-convenience-20261020, branch codex/dldws001-ui-convenience-20261020, HEAD 37cb16030930f7fe7edd7c8fa9423b4e0f90e9dc.
TASK: DLDWS-001; CONTRACT_VERSION: 1.0.0; REQUIRES_WORKSTREAMS: downloader,discovery-writer-safety.
APPROVED_SCOPE:
- Publish the failed-download bulk retry UI/API, shared queue-admission locking and duplicate prevention, ENOSPC/inode fail-closed checks, and synthetic fragment preservation checks.
- Publish bounded, redacted SpoofDPI early-exit diagnostics without changing its launch arguments or network route.
- Include only the necessary Dockerfile/UI patch integration and focused tests.
- Preserve existing Selkies restart behavior, individual download retry behavior, settings save behavior, and max_concurrent=4.
PROHIBITED: Do not publish any Downloader server-restart UI/API, Docker restart helper, service/socket, privilege or management control path. Do not build/deploy images, restart or replace production containers, run downloads/retries, or change Writer, Gluetun, Stage11, NAS/Jellyfin, or operational data.
VALIDATION: Reuse the recorded Flask route integration and Chromium 10-scenario evidence; run focused syntax, bulk retry/SpoofDPI smoke, final UI patch validation, and git diff --check for the exact selected publication set.
EXECUTION_STATUS: AUTHORIZED; canonical code publication pending approval-record readback and focused prepublication validation.


## SEPARATE APPROVED EXECUTION RESULT — Canonical publication (2026-10-20)

USER_APPROVAL: The user explicitly approved publishing only the verified failed-download bulk retry UI/API and bounded SpoofDPI early-exit diagnostics.
CANONICAL_CODE_PUBLISH=PASS
CODE_COMMIT=453011a0f9c71ccf7a4ab6cfef96b375213211a1
BULK_RETRY=PASS
SPOOFDPI_DIAGNOSTIC=PASS
SERVER_RESTART_FEATURE=EXCLUDED
CANONICAL_READBACK=PASS (12/12 published product/build/test files read back with matching Git blob hashes)
PRODUCTION_DEPLOYMENT=NOT_RUN
REAL_DOWNLOAD_TEST=NOT_RUN
OPERATING_RESOURCE_CHANGES=NONE

PUBLISHED_FILES:
- Dockerfile
- app.py
- teddy_entrypoint.py
- teddy_patch_index.py
- teddy_routing.py
- teddy_downloader_admin.py
- teddy_patch_downloader_admin.py
- teddy_downloader_admin_smoke.py
- teddy_downloader_admin_flask_smoke.py
- teddy_spoofdpi.py
- templates/index.html
- templates/teddy-reliability.js

VALIDATION: Reused the recorded Flask route integration and 10-scenario Chromium evidence. Focused synthetic bulk-retry/SpoofDPI smoke, Python syntax, JavaScript syntax (Node.js v24.22.0), ordered Dockerfile UI patch-chain validation, and git diff --check passed. No Docker image was built; no production container, download, queue, or operational data was changed. Existing Selkies restart and individual-download retry remain; max_concurrent=4 is preserved.
NEXT: Any Docker image build or production deployment requires a separate user approval.


## SEPARATE APPROVED EXECUTION — Final Docker image build and Downloader deployment (2026-10-20)

USER_APPROVAL: The user explicitly approved building a new Docker image from canonical source, replacing only the existing Downloader container, validating HTTP/UI/data preservation, and one safe rollback if required.
CANONICAL_BASE: b3494130fcf504bf468113dede75e86b17655b98
PRODUCT_COMMIT: 453011a0f9c71ccf7a4ab6cfef96b375213211a1
TASK: DLDWS-001; CONTRACT_VERSION: 1.0.0; REQUIRES_WORKSTREAMS: downloader,discovery-writer-safety.
APPROVED_SCOPE: Build and inspect the verified bulk-retry/SpoofDPI candidate from a clean canonical worktree; if all required preflight checks pass, deploy that exact image to Downloader service `missav-dlp-web` only; verify runtime/UI/data and roll back once if material failure requires it.
PROHIBITED: Downloader server-restart UI/API/helper; bulk-retry execution or real downloads; modifying existing jobs/fragments/settings; changing Writer, Gluetun, Selkies, NAS/Jellyfin or Stage11; replacing any service other than Downloader; altering or deleting the existing backup.
PRECONDITIONS: Confirm CT108 identity and Docker engine access; verify the pinned prior/new image, actual Compose inputs and secrets without disclosure, backup archive/readback, current task/fragment hashes and storage capacity; no in-flight download/retry/MP4 work; compose delta is image-only; build output excludes Downloader server restart control. Stop without operational mutation if any check is unknown or fails.
EXECUTION_STATUS=AUTHORIZED; approval-record readback required before build/deploy. Deployment is allowed only after all preconditions PASS.


## SEPARATE APPROVED EXECUTION RESULT — Final Docker image deployment (2026-10-20)

USER_APPROVAL: The user explicitly approved one canonical Docker image build, replacement of the Downloader container only, operational HTTP/UI/data checks, and one safe rollback if required.
APPROVAL_RECORD=PASS; APPROVAL_COMMIT=d307ddac86c94f1741d72f5afb07893ea94c1690; APPROVED_SOURCE_PRODUCT_COMMIT=453011a0f9c71ccf7a4ab6cfef96b375213211a1.
PRE_DEPLOY_GATE=FAIL
BLOCK_REASON: The available shell reports hostname `downloader` and LXC virtualization, but its cgroup does not establish CT108 identity. The default Docker daemon endpoint is `unix:///var/run/docker.sock` and read-only `docker info`/inspect requests returned permission denied. The execution environment therefore cannot confirm or query the authorized CT108 Docker engine.
IMAGE_BUILD=NOT_RUN
IMAGE_VERIFICATION=NOT_RUN
PRODUCTION_DEPLOYMENT=NOT_RUN
BACKUP_RECHECK=NOT_RUN
DOWNLOADER_HTTP=NOT_RUN
BULK_RETRY_UI=NOT_RUN
SPOOFDPI_DIAGNOSTIC=NOT_RUN
SERVER_RESTART_FEATURE=EXCLUDED
JOB_STATE_PRESERVED=UNKNOWN
FRAGMENTS_PRESERVED=UNKNOWN
MAX_CONCURRENT=UNKNOWN
WRITER_INTEGRATION=NOT_RUN
GLUETUN_PRESERVED=UNKNOWN
REAL_DOWNLOAD_TEST=NOT_RUN
ROLLBACK=NOT_NEEDED (no deployment attempt)
OLD_IMAGE_ID=NOT_VERIFIED; NEW_IMAGE_ID=NOT_BUILT; DEPLOYED_SOURCE_SHA=NONE.
OPERATIONAL_RESOURCES_CHANGED=NONE_BY_THIS_EXECUTION.

No Docker permission workaround, privilege escalation, service/configuration change, backup access, build, or deployment was attempted after the access denial. The production state and backup were not re-inspected because the required Docker API/CT108 preflight could not be completed. The deployment remains blocked until an authorized execution session can verify CT108 and access its Docker API without changing or bypassing permissions.
NEXT: Resume the approved preflight from a verified CT108 session with its existing authorized Docker access; rerun the full read-only gates before any build or deployment.


## SEPARATE APPROVED EXECUTION — Writer smoke inode reuse validation (2026-10-21)

> TASK_ID: DLDWS-001
> CONTRACT_VERSION: 1.0.0
> REQUIRES_WORKSTREAMS: downloader,discovery-writer-safety
USER_APPROVAL: Isolated modification and offline verification of teddy_library_discovery_writer_smoke.py only, based on c4c00605af6ea7ae9109a99ae39e8ecf76fd5c30. Replace inode-inequality assumptions with real socket type/mode, shutdown/cleanup, health, DB/replay and active-listener preservation evidence. Exercise replacement races, including reused/colliding identities, without weakening or skipping safety assertions. Preserve all prior evidence and protected candidates.
BOUNDARY: Use a new isolated working tree, temporary synthetic sockets and databases, preferably Python 3.10. No production Writer code edits, canonical test-code publication, Docker build/deployment, service restart, operational socket/DB/data changes, Stage11 or NAS/Jellyfin work. Record any actual unsafe unlink as FAIL/BLOCKED; do not manufacture a pass.
EXECUTION_STATUS: AUTHORIZED; implementation starts only after matching approval records are remotely read back.


## SEPARATE APPROVED EXECUTION RESULT — Writer smoke inode reuse validation (2026-10-21)

> TASK_ID: DLDWS-001
> CONTRACT_VERSION: 1.0.0
> REQUIRES_WORKSTREAMS: downloader,discovery-writer-safety
WRITER_SMOKE_ROOT_CAUSE=CONFIRMED
INODE_REUSE_ASSUMPTION=REMOVED
ACTIVE_LISTENER_SAFETY=FAIL
REPLACEMENT_RACE_SAFETY=FAIL
STALE_SOCKET_RECOVERY=PASS
WRITER_SMOKE=FAIL
EXISTING_REGRESSIONS_BEFORE_COLLISION=PASS
UNCHANGED_ACTIVE_LISTENER_GUARD=PASS
UNSAFE_UNLINK_MUTATION_DETECTION=PASS
PYTHON_SYNTAX=PASS
GIT_DIFF_CHECK=PASS
BUILD_FILESYSTEM_REPRODUCTION=INCOMPLETE
PRODUCTION_WRITER_CODE=UNCHANGED
DOCKER_IMAGE_BUILD=NOT_RUN
PRODUCTION_DEPLOYMENT=NOT_RUN
TEST_CODE_CANONICAL_PUBLICATION=NOT_RUN
OPERATIONAL_RESOURCE_CHANGES=NONE

CANDIDATE: /tmp/dldws001-writer-smoke-20261021, branch codex/dldws001-writer-smoke-20261021, base c4c00605af6ea7ae9109a99ae39e8ecf76fd5c30. Only teddy_library_discovery_writer_smoke.py is modified and uncommitted. Existing release worktree remains clean; protected candidates were not edited.

ROOT CAUSE: The supplied CT108 build log fails at original line 243's inode-inequality assertion after the old pathname was removed and a new server bound. A new socket generation need not have a different identity tuple. The restart and stale-recovery checks now verify closed old FD/thread, cleanup and parent boundaries, real socket type/0660/UID/GID/listening FD/health, and the existing DB snapshot/ALREADY_RECONCILED checks. The race inequality was replaced with actual replacement bind/listen/READY, unchanged path/parent/metadata, post-cleanup health, no cleanup unlink and required fail-closed response.

SAFETY FAILURE: Python 3.10.22 executed all existing protocol, DB/replay, restart, stale recovery, active-listener, wrong-type/symlink, ownership, probe-error, distinct replacement and parent-directory race assertions successfully. The added mandatory identity-collision race then FAILS: the replacement was listening and health READY before cleanup, but unchanged canonical _prepare_socket_parent performed one actual dir_fd-based unlink and removed the active listener's pathname while its FD was still listening. Only the identity-key function was aliased to model reuse; bind/listen/health, stat type/owner and unlink were real. A separate unsafe-unlink mutant that even returned WRITER_UNAVAILABLE was also detected. This full smoke failure is preserved; production code was not edited or mocked into a pass.

ENVIRONMENT: The local baseline passed on tmpfs with Python 3.10.22; 32 physical unlink/rebind observations produced 0 equal identities. Docker's filesystem condition was not reproduced, and no Docker rebuild ran. The colliding-key case is deterministic synthetic evidence of the implementation defect, not a claim of locally observed physical inode reuse. The initial sandbox bind denial was recorded separately; socket-enabled isolated tests used temporary paths and synthetic DBs only. No production Writer safety conclusion is inferred for its separately deployed implementation.

EVIDENCE: /tmp/dldws001-writer-smoke-evidence-20261021-8u4jd832/validation-summary.json (SHA-256 6ce9c4d503231c5fef864077da0b6cb83260a6ad76bb0d69d663fceb963b77f2); modified-python310-full.log (b8e69a40ca8e3e1407e7093cda88d68605b3e9a50368ba23ebc13592329686df); collision-mutation-controls.json (8becbb282dd6845b20ddbbb9fc0b3e23a0dc3a69c27fde244759f0697d662a84); comparison.md and writer-smoke.patch. Candidate smoke SHA-256: d1a20a2ad8435499914d5faf238a8f9da5a693b27c0304f40b22d92f854d34b4. Unchanged Writer source SHA-256: 8898087c4830a6e2729c5593377224a9cfa518147aa0ec40bdc554cba392410e. Supplied build log SHA-256: 525ea73e7df2f9f617a767cfffb92b8f9622edf85347dc3648b1868f12057b7a.

NEXT: Obtain separate scope approval to fix or replace the canonical direct socket cleanup path so it refuses active replacement cleanup even when identity keys collide. Do not build/deploy or publish this failing test candidate automatically.


## SEPARATE APPROVED EXECUTION — Active socket replacement race fix (2026-10-21)

> TASK_ID: DLDWS-001
> CONTRACT_VERSION: 1.0.0
> REQUIRES_WORKSTREAMS: downloader,discovery-writer-safety
USER_APPROVAL: Implement and verify an isolated fix for active-listener unlink caused by stale-check/path-replacement races and colliding socket identities. Use a new working tree based on 6d02dbcc22367cd184017a6e0b5d451f0cd3e9d1; preserve the failed smoke candidate/evidence and all existing protected candidates.
APPROVED_SCOPE: teddy_library_discovery_writer.py and teddy_library_discovery_writer_smoke.py, plus a narrowly scoped Writer-only synthetic safety test if necessary. Transplant the mandatory prior replacement/collision checks without weakening them. Validate actual listener/path/health preservation, no unlink, last-check races, parent/type/owner/probe boundaries, Python 3.10 multiprocess contention and DB replay.
SAFETY_BOUNDARY: Neither extra stat/connect checks nor advisory locks prove protection against a noncooperating replacement. If safe automatic stale cleanup cannot be proved, fail closed and report the stale-recovery/design conflict as BLOCKED; retain the recovery test failure instead of redefining it as PASS. Reuse existing verified lifetime mechanisms only within this scope; do not invent a broad architecture.
PROHIBITED: Canonical product-code publication, Docker build/deployment, operational socket/service/systemd/DB/download/data changes, modifications to protected candidates, Stage11, NAS/Jellyfin, test skips or weakened safety expectations.
EXECUTION_STATUS: AUTHORIZED; implementation begins after matching approval records are remotely read back.


## SEPARATE APPROVED EXECUTION RESULT — Active socket replacement race fix (2026-10-21)

> TASK_ID: DLDWS-001
> CONTRACT_VERSION: 1.0.0
> REQUIRES_WORKSTREAMS: downloader,discovery-writer-safety
WRITER_RACE_FIX=BLOCKED
ACTIVE_LISTENER_SAFETY=PASS
IDENTITY_COLLISION_SAFETY=PASS
REPLACEMENT_RACE_SAFETY=PASS
MULTIPROCESS_SAFETY=PASS
STALE_SOCKET_RECOVERY=FAIL
WRITER_SMOKE=FAIL
DB_REPLAY_REGRESSION=PASS
UNSAFE_UNLINK_MUTATION_DETECTION=PASS
PYTHON_SYNTAX=PASS
GIT_DIFF_CHECK=PASS
PRODUCTION_WRITER=UNCHANGED
CANONICAL_PRODUCT_CODE=NOT_PUBLISHED
DOCKER_IMAGE_BUILD=NOT_RUN
PRODUCTION_DEPLOYMENT=NOT_RUN
OPERATIONAL_RESOURCE_CHANGES=NONE

CANDIDATE: /tmp/dldws001-writer-race-fix-20261021, branch codex/dldws001-writer-race-fix-20261021, base 6d02dbcc22367cd184017a6e0b5d451f0cd3e9d1. Only teddy_library_discovery_writer.py, teddy_library_discovery_writer_smoke.py and the new Writer-only teddy_library_discovery_writer_race_smoke.py differ; all remain uncommitted in the isolated candidate. The previous failing smoke was transplanted exactly (SHA-256 d1a20a2ad8435499914d5faf238a8f9da5a693b27c0304f40b22d92f854d34b4), without deleting/skipping/changing its requirements. Prior failure evidence hashes still match; release and B-option working trees remain clean.

SAFE BOUNDARY: Replaced only _prepare_socket_parent's automatic unlink block with WRITER_UNAVAILABLE. Existing type/owner/parent/probe and already-disappeared-path handling remain. There is no unlink call left in the Writer implementation, so this cleanup path cannot delete a noncooperating replacement after the last check, with or without colliding metadata. No advisory lock or repeated stat/connect is claimed to make deletion atomic. Fresh Unix bind arbitrates competing creators without deleting the losing process's path. This does not prevent unrelated processes from deleting a path themselves.

VERIFICATION: Python 3.10.22 ran 8 focused tests successfully: real active-listener preservation; both unchanged distinct/colliding replacement fixtures; real replacement after the final lstat result was captured; parent/type/symlink/owner and EACCES/EAGAIN/ETIMEDOUT/EIO boundaries; DB preflight/RECONCILED/replay/ALREADY_RECONCILED; and detection of an unsafe unlink mutant even if it returns WRITER_UNAVAILABLE. Real path/listen/health and no-unlink checks passed. Six independent spawned Python processes exercised two simultaneous fresh starts (one listener, one EADDRINUSE), two cleanup attempts against that active winner, and two against its retained stale path after shutdown. All exited normally with zero unlink calls; the winner kept its path and health READY after concurrent cleanup attempts. Syscall spy wrappers passed through real operations; no mock socket/backend replaced these checks.

COMPATIBILITY BLOCK: The preserved entire Writer smoke returns 1 at line 316, where direct-mode restart requires automatic stale cleanup. The safe candidate refuses the retained stale socket with WRITER_UNAVAILABLE. Thus normal direct-mode restart after a retained path and automatic stale recovery are not restored: STALE_SOCKET_RECOVERY=FAIL, WRITER_SMOKE=FAIL and overall BLOCKED. The recovery test has not been relaxed. DB_REPLAY_REGRESSION=PASS is scoped to a separate synthetic test using explicit fixture-owned cleanup after its sole server was closed; it is not automatic Writer recovery evidence.

DESIGN DECISION REQUIRED: The current direct-mode interface has no exclusive pathname-lifecycle authority against noncooperating replacements. Safe automatic unlink was not demonstrated. The existing B-option delegates path ownership to systemd and adopts an inherited FD, but its legacy cleanup is unchanged; it was inspected read-only and not imported or deployed. Decide whether to retire direct-mode automatic reclamation and align canonical startup with the already tested systemd-owned lifecycle before implementing compatibility changes. Do not publish/build/deploy this blocked candidate.

EVIDENCE: /tmp/dldws001-writer-race-fix-evidence-20261021-8_n_7ns6/validation-summary.json, SHA-256 d7a7adee3ddc2570e5b770904304bb1947e05388a4286fb1334602cac0ce45d4; race-safety-python310.log (4c5935c8b94f57d1852d9c415202b91c2412f7150214f447ec22bb27b853056a); preserved-full-writer-smoke-python310.log (10377bfa5c5812db715d6ed9cc7ae13c78dc77176a575fb8675ad7ccea790635); safety-and-compatibility.md plus both candidate patches. Candidate Writer SHA-256 b8f6f638231bb13bb8dabcb5a3bb28907d515985c3ab8d17109cb801311c5c55; new race smoke SHA-256 bf004f58dde5e96c231602f2f86fff8f297fef4fdf526b01909eba38e60e5662.

NEXT: User decision on retiring automatic direct-mode stale cleanup and using the existing systemd-owned socket lifecycle; no further implementation or operational change follows automatically.


## SEPARATE APPROVED EXECUTION — Legacy image eight-file overlay candidate (2026-10-21)

> TASK_ID: DLDWS-001
> CONTRACT_VERSION: 1.0.0
> REQUIRES_WORKSTREAMS: downloader,discovery-writer-safety
USER_APPROVAL: Prepare and verify an isolated derivative of parent image sha256:83322ee82e736b5ba026b8d98d5709b9685ca9c6b051c2a7f4c7b9bf8d058573 for failed-download bulk retry UI/API and bounded redacted SpoofDPI diagnostics, using final runtime snapshot /tmp/dldws001-legacy-runtime-20261021 and feature commit 453011a0f9c71ccf7a4ab6cfef96b375213211a1.
RUNTIME_ALLOWLIST: /app/app.py, /app/teddy_entrypoint.py, /app/teddy_routing.py, /app/teddy_bootstrap.py, /app/templates/index.html, /app/templates/teddy-reliability.js, /app/teddy_downloader_admin.py, /app/teddy_spoofdpi.py only. Keep build recipe, tests and manifests outside copied runtime. Preserve authentication/CSRF, shared queue/state locks on all admission routes, MP4/ENOSPC/fragment protections, health-only, routing, Selkies and max_concurrent=4.
BOUNDARY: New isolated directory; no changes to original snapshots/candidates. Allow an isolated no-network Docker build and synthetic tests only, with exact parent and final filesystem-difference verification. If Docker access is denied, do not escalate or change permissions: record build BLOCKED and provide an operator build command; host-only evidence does not count as final-image evidence.
PROHIBITED: Production container/image/Compose/service/data changes, real retry/download/MP4 work, Docker pull or package installation, docker commit, canonical product publication, any Writer change or Writer safety PASS/full canonical-build PASS claim, reintroduction of Downloader server restart, Stage11/NAS/Jellyfin/backup changes.
EXECUTION_STATUS: AUTHORIZED; candidate edits start only after matching approval records are remotely read back. Writer race and full canonical-build findings remain unresolved and preserved.

## RESULT — Legacy image eight-file overlay candidate, Docker access blocked (2026-10-21)

Shared task DLDWS-001; contract 1.0.0; matching scope downloader,discovery-writer-safety. Execution approval was published and read back at 09ccfa8fb1f618af1c5c6409b9c4b0e574acd6a7. Existing approvals, failures, deployment evidence and Writer race findings remain preserved.

OVERLAY_BUILD=BLOCKED. A read-only image inspection was denied at unix:///var/run/docker.sock. No Docker permission change or escalation was attempted; no build, image creation, image save, test container or production container operation occurred. The approved parent sha256:83322ee82e736b5ba026b8d98d5709b9685ca9c6b051c2a7f4c7b9bf8d058573 could not be independently inspected in the current Docker session. NEW_IMAGE_ID=NONE. Planned tag only: missav-dlp-web:dldws001-legacy-overlay-20261021 (not created).

CANDIDATE: /tmp/dldws001-legacy-overlay-20261021. Exactly eight runtime files are staged in context/runtime: app.py, teddy_entrypoint.py, teddy_routing.py, teddy_bootstrap.py, templates/index.html, templates/teddy-reliability.js, teddy_downloader_admin.py, teddy_spoofdpi.py. All six protected snapshot SHA-256 values match; original clean release checkout at c4c00605af6ea7ae9109a99ae39e8ecf76fd5c30 includes feature 453011a0f9c71ccf7a4ab6cfef96b375213211a1 and remains clean. No whole-file canonical replacement was applied over the built runtime. Eight candidate hashes and source/parent provenance are in manifest.json. Eighty-seven other existing Python function bodies remain unchanged.

HOST-ONLY VALIDATION: Python 3.10.22 synthetic suite PASS, 12 test methods. Actual Flask test_client + existing auth + installed bulk routes exercise login, session CSRF, selection, actual legacy MP4-aware retry callback, shared existing task-state lock, auto/manual/bulk admission race, routing/new-task/resume serialization, queue deduplication, unknown lock/MP4 fail-closed, storage/inode failures, partial results and fragment preservation. The unchanged MP4 queue lock was exercised by three separate synthetic processes without media conversion. Existing health-only guards and bootstrap authentication order remain intact. SpoofDPI fake-process tests preserve argv and two-second observation, bounded output, exit-code diagnostics and credential/URL/IP redaction. No normal app import, download/MP4 worker, operational data mount or external network request was used.

BROWSER: Chromium 156.0.8078.4 / Node v24.22.0, ten synthetic mock-API scenarios PASS, desktop 1440x900 and mobile 390x844. Confirm/cancel, duplicate-click protection, partial results, storage/inode errors, refresh, existing individual retry/settings save and absence of Downloader server restart were verified. Zero uncaught JavaScript errors or unexpected console errors; three console events were expected negative HTTP responses. The initial sandbox loopback bind EPERM and successful isolated localhost run are separately preserved. Existing tool dependencies were reused without installation.

BUILD-PROOF TOOLING: Explicit eight-COPY, local image-ID FROM Dockerfile; no package install, repository COPY, pull, RUN, docker commit or full canonical Dockerfile. build_candidate.py is prepared but not executed: checks parent/image-store space/tag collision/input hashes, performs one offline build, validates saved-image parent layers/eight-file delta/Writer hashes, then runs the same synthetic suite against the final image without normal app startup. Its archive verifier passed two host synthetic tests, rejecting five unsafe mutations. This tooling is not evidence of an actual image build or final-image PASS.

FINAL-IMAGE STATUS: Parent local-presence verification BLOCKED; filesystem delta, Writer hash readback and image-internal execution NOT_RUN. FLASK_AUTH_CSRF=PASS, QUEUE_RACE_SAFETY=PASS, MP4_ENOSPC_FRAGMENT_SAFETY=PASS, SPOOFDPI_DIAGNOSTIC=PASS and UI_DESKTOP_MOBILE=PASS refer only to the executed host candidate checks. No Writer file was changed or included in the overlay; WRITER_SAFETY_ISSUE=UNRESOLVED. SERVER_RESTART_FEATURE=EXCLUDED. This is not a full canonical-build PASS.

EVIDENCE: manifest.json; evidence/result.json; evidence/artifact-audit.json; evidence/runtime.patch; evidence/host-offline-results.json and host-offline.log; evidence/browser/browser-results.json and synthetic desktop/mobile screenshots; evidence/build-proof-tests.log; evidence/artifact-hashes.json. Syntax and runtime diff whitespace checks PASS. README.md explains all limits and the unexecuted operator path.

PRODUCTION_DEPLOYMENT=NOT_RUN; REAL_DOWNLOAD_TEST=NOT_RUN; canonical product publication NOT_RUN; operational writes by this execution NONE. Existing Downloader/Writer/Gluetun/Selkies, user max_concurrent=4, download records/fragments, backup, NAS/Jellyfin and Stage11 were not touched.

NEXT: In an authorized root@downloader session with existing Docker access, run once:
python3 /tmp/dldws001-legacy-overlay-20261021/build_candidate.py
Preserve the new image ID and final-image evidence; do not deploy. If the fixed local-image-ID legacy builder or any safety verification fails, stop without fallback, pull or automatic retry.

RECORD FORMAT: Structural validation found historical TASK_ID/CONTRACT_VERSION/REQUIRES_WORKSTREAMS lines duplicated as live metadata in both existing ACTIVE_WORK records (five copies before this execution approval, six afterwards). Every value matched the current DLDWS-001 / 1.0.0 / downloader,discovery-writer-safety metadata. Historical copies are now blockquoted without changing their values or evidence; only the first live header remains machine metadata. No contract, router, workstream state or authorization scope was changed.

## SUPPLEMENTAL SAFETY GATE — State-file ENOSPC silently accepted by legacy retry (2026-10-21)

Shared scope remains DLDWS-001, contract 1.0.0, downloader,discovery-writer-safety. Preserve the previous 12 host test PASS results and ten browser PASS scenarios, but they are insufficient for the overall candidate safety gate. This supplemental finding supersedes the preceding suggestion to proceed directly to an operator build.

CONFIRMED SYNTHETIC FAILURE: The exact candidate app.py save_tasks body catches every Exception and discards state-file write errors. A separate regression used the actual extracted save_tasks and actual legacy safe_retry_task callback through the installed/authenticated Flask bulk API. Only synthetic state, auth and fragment files were used. Injecting ENOSPC at state-file open returned HTTP 200, succeeded=1, failed=0 and queued one task. The old on-disk synthetic record and fragment remained unchanged, but the in-memory record/retry count changed. Persistence failure was not observable by the retry callback. This is an inherited legacy persistence behavior exposed by the new bulk path, not evidence that production experienced an ENOSPC write during this investigation.

STATE_PERSISTENCE_SAFETY=FAIL. MP4_ENOSPC_FRAGMENT_SAFETY=FAIL for the aggregate candidate gate; MP4 protection, byte/inode preflight and synthetic fragment-preservation checks themselves retain their narrower PASS evidence. FLASK_AUTH_CSRF=PASS; QUEUE_RACE_SAFETY=PASS; SPOOFDPI_DIAGNOSTIC=PASS; UI_DESKTOP_MOBILE=PASS, all host-only. Total host safety methods: 12 PASS plus this additional FAIL. The failing assertion and result are preserved, not removed, skipped or converted into expected success.

OVERLAY_BUILD=BLOCKED for both Docker API denial and this confirmed safety gap. NEW_IMAGE_ID=NONE; CHANGED_RUNTIME_FILES=8 in the isolated source candidate only. build_candidate.py now rejects the failed persistence gate before making any Docker call. The direct Docker command in README is documentation only and must not bypass that guard. No image build or final-image execution occurred.

SCOPE STOP: The app.py allowlist authorized SpoofDPI diagnostics, shared admission lock and auto-retry serialization; it did not authorize redesigning the existing task-file persistence policy. Do not silently add a new writer or globally change normal startup/download error propagation. Determine the smallest approved correction that makes failed state persistence reject queue admission and preserves existing records, then rerun the retained failing regression before building. No further product edits were made after confirming this failure.

EVIDENCE: /tmp/dldws001-legacy-overlay-20261021/tests/state_persistence_probe.py; evidence/state-persistence-probe.json; evidence/state-persistence-probe.log; updated evidence/result.json, README.md and guarded build_candidate.py. The original six snapshot hashes remain unchanged, release checkout remains clean and all runtime changes remain within the eight-file candidate. No Writer runtime file was changed; Writer safety remains UNRESOLVED.

PRODUCTION_DEPLOYMENT=NOT_RUN; REAL_DOWNLOAD_TEST=NOT_RUN; production resource writes NONE; canonical product publication NOT_RUN. Existing Downloader, settings/max_concurrent=4, task records, fragments, Writer/Gluetun/Selkies, backups and Stage11 remain untouched by this work.

NEXT: Approve the minimal persistence/admission safety correction and revalidate the preserved failing ENOSPC regression. Do not build or deploy this candidate while the safety gate is FAIL.

## SEPARATE APPROVED EXECUTION — Retry state persistence failure correction (2026-10-21)

Shared task DLDWS-001; contract version 1.0.0; required workstreams downloader,discovery-writer-safety. User-approved isolated correction follows the preserved ENOSPC failure recorded in the previous result. Existing failure evidence must remain unchanged.

OBJECTIVE: A retry may enter the download queue only after its updated task state has been durably and verifiably saved. On storage failure, reject queue admission and preserve the prior task file bytes, in-memory task record/retry count, and existing parts data.

ALLOWED PRODUCT SCOPE: Modify only the minimum existing files among the already approved eight-file legacy overlay runtime set, specifically app.py, teddy_entrypoint.py, teddy_downloader_admin.py if necessary. A retry-only checked/atomic state persistence path is permitted; a global rewrite of save_tasks or a general persistence framework is not. Keep changes isolated under /tmp/dldws001-legacy-overlay-persist-20261021. Existing failure test/evidence under /tmp/dldws001-legacy-overlay-20261021 are immutable. New synthetic tests, test-only gate changes, and evidence are permitted.

REQUIRED CHECKS: Retain and pass state_persistence_probe.py semantics; cover ENOSPC at open, partial write, flush/fsync, replace, and post-replace durability failure where safely injectable; confirm prior task-file bytes/hash, per-task memory state, queue, and parts hashes; exercise successful retry; retain auth/CSRF, MP4, capacity/inode, shared-lock and duplicate-queue checks. Do not overwrite unrelated task state during rollback. If restoration after an uncertain replace cannot be proven, fail closed and report the precise remaining limitation.

PRESERVE: Existing 12 synthetic host PASS results, ten Chromium scenarios, the original failing probe/result, all prior approvals and Writer failure history. UI/SpoofDPI/Writer changes are excluded. Maximum download concurrency stays 4. No Downloader server restart control is added.

PROHIBITED: Docker build, production deployment/restart/retry/download, production or NAS/Jellyfin/Stage11/Writer data/service changes, canonical product publication, test deletion/skip/weakening, global save_tasks policy change, or widening beyond the existing eight runtime files.

EXECUTION_STATUS: AUTHORIZED only after this matching approval block is remotely read back from both workstreams. The previous build failure remains unresolved until the retained persistence regression passes. Even if this correction passes, no image build is authorized in this execution.


## EXECUTION RESULT — DLDWS-001 ENOSPC retry state persistence correction (2026-10-21)

ISOLATED_RESULT=PASS
STATE_PERSISTENCE_SAFETY=PASS
ENOSPC_RETRY_BLOCK=PASS
MEMORY_STATE_PRESERVED=PASS
TASK_FILE_PRESERVED=PASS
QUEUE_UNCHANGED_ON_FAILURE=PASS
FRAGMENTS_PRESERVED=PASS
AUTO_MANUAL_BULK_RACE=PASS
FLASK_AUTH_CSRF=PASS
MP4_ENOSPC_SAFETY=PASS
OVERLAY_SAFETY_GATE=PASS
DOCKER_IMAGE_BUILD=NOT_RUN
PRODUCTION_DEPLOYMENT=NOT_RUN
WRITER_SAFETY_ISSUE=UNRESOLVED

The isolated candidate is `/tmp/dldws001-legacy-overlay-persist-20261021`. Only `app.py` and `teddy_entrypoint.py` changed among the eight allowlisted runtime files. Retry persistence is checked through same-directory temporary write, flush/fsync, readback, atomic replacement and directory fsync before queue admission. On tested failures, the affected in-memory task and retry count, previous task-file bytes, queue, and synthetic parts remain unchanged. The legacy global `save_tasks()` policy is unchanged.

Evidence: retained failure replay now reports succeeded=0, failed=1, queue_entries=0; persistence fault injection 11/11 PASS; existing Python 3.10.22 host regression suite 12/12 PASS. Existing Chromium 10-scenario PASS was reused without rerun because no HTML/JavaScript changed. Prior failing evidence remains preserved with SHA-256 `d32e553ce3150f8bd7727e9066ad54b656174962531ef8f0d366e8d18909e3f1`.

Limitation: if directory fsync fails after replacement and also during rollback, retry is denied and the tested live task bytes/memory and queue are restored, but crash durability remains UNKNOWN while the filesystem persistently rejects fsync; manual reconciliation is required.

No production resource changed. Canonical product code was not published. Next action requires a separate approval for Docker build and final-image offline verification; this execution does not authorize either.


## SEPARATE APPROVED EXECUTION — legacy image overlay build and final offline verification

APPROVAL_DATE: 2026-10-22
AUTHORIZATION: Explicit user approval in the DLDWS-001 overlay-build request.
CANONICAL_BASE: e4460e140d4bb7882b0fdea64a09dca90c610809
> TASK_ID: DLDWS-001
REQUIRED_WORKSTREAMS: downloader,discovery-writer-safety

This separate execution authorizes only an isolated overlay build based on the verified candidate /tmp/dldws001-legacy-overlay-persist-20261021 and final-image offline verification. The source candidate is immutable. Build and evidence output must go to a fresh isolated copy at /tmp/dldws001-overlay-build-20261022 and its own evidence directory. Use the exact local parent image ID sha256:83322ee82e736b5ba026b8d98d5709b9685ca9c6b051c2a7f4c7b9bf8d058573; reserve only the new tag missav-dlp-web:dldws001-legacy-overlay-persist-20261022.

### AUTHORIZED_SCOPE
- Verify the source candidate manifest, hashes, prior persistence/host/browser evidence, parent image, disk and inode capacity, and existing Downloader container state before building.
- Reuse only the allowlisted eight runtime files. Prove the final image adds/replaces exactly those eight files, preserves the exact parent layers and inherited runtime configuration, and leaves Discovery Writer files unchanged.
- Build one isolated candidate image with no pull, external network, package installation, docker commit, production volume, or source-candidate mutation.
- Run only bounded, network-disabled synthetic tests against that final image. Record any verification that cannot safely be completed as INCOMPLETE.
- If Docker API access is denied or any preflight is unknown, stop without privilege escalation and record BLOCKED_DOCKER_ACCESS or the specific gate.

### PROHIBITED_SCOPE
No production deployment, Downloader container start/restart/replace, download or bulk retry, production data or parts access, Writer/Gluetun/Selkies/Stage11/NAS/Jellyfin changes, existing image deletion, canonical product code publication, or Writer safety fix. The known Writer race and full canonical Dockerfile smoke failure remain unresolved; this overlay cannot be reported as resolving them. No retry of a failed build or test without a new decision.

### ACCEPTANCE_AND_BOUNDARIES
Report the exact parent and new image IDs, allowlisted runtime diff, final-image offline test results, UI evidence and its provenance, Writer-file immutability, existing production container immutability, and unresolved gaps. Keep this approval active only for this one isolated build/verification execution. It does not authorize operational deployment.


## EXECUTION RESULT — DLDWS-001 overlay build and final offline verification (2026-10-22)

OVERLAY_BUILD=BLOCKED
PARENT_IMAGE_ID=sha256:83322ee82e736b5ba026b8d98d5709b9685ca9c6b051c2a7f4c7b9bf8d058573 (pinned in manifest; local daemon inspect NOT_RUN)
NEW_IMAGE_ID=NONE
RUNTIME_FILE_DIFF=INCOMPLETE (source context contains exactly the eight allowlisted files with matching hashes; final image layer proof NOT_RUN)
FLASK_AUTH_CSRF=INCOMPLETE (candidate host suite included this and passed 12/12; final image NOT_RUN)
STATE_PERSISTENCE_SAFETY=INCOMPLETE (candidate fault suite 11/11 and retained ENOSPC probe PASS; final image NOT_RUN)
QUEUE_RACE_SAFETY=INCOMPLETE (candidate host suite PASS; final image NOT_RUN)
MP4_ENOSPC_FRAGMENT_SAFETY=INCOMPLETE (candidate host suite PASS; final image NOT_RUN)
SPOOFDPI_DIAGNOSTIC=INCOMPLETE (candidate host suite PASS; final image NOT_RUN)
UI_VALIDATION=INCOMPLETE (prior Chromium 10/10 PASS reused candidate UI hashes; final image linkage NOT_RUN)
WRITER_FILES_UNCHANGED=YES in the source overlay allowlist; final image NOT_VERIFIED
PRODUCTION_CONTAINER_UNCHANGED=YES (no Docker-mutating command was issued; live state inspection NOT_RUN)
PRODUCTION_DEPLOYMENT=NOT_RUN
REAL_DOWNLOAD_TEST=NOT_RUN
WRITER_SAFETY_ISSUE=UNRESOLVED

The source candidate manifest SHA-256 is a2b5c134528aea387fc93fd8d25c56e88c5c1a47c6408562536dd4fd9ab60b7f. All eight runtime hashes and the nine-file Docker context (Dockerfile plus eight runtime inputs) matched; the earlier failing-probe evidence SHA-256 d32e553ce3150f8bd7727e9066ad54b656174962531ef8f0d366e8d18909e3f1 remains preserved. The source candidate was not modified.

Docker access was denied by a read-only docker info call in hostname downloader, LXC, UID 0/GID 0: permission denied connecting to /var/run/docker.sock (mode 0660, owner 0:65534). No permission change or escalation was attempted. Parent image and production container inspect, build, image run, and final-image tests therefore were not run.

A separate byte-verified build copy is prepared at /tmp/dldws001-overlay-build-20261022. Its only build-script change is the unique candidate tag missav-dlp-web:dldws001-legacy-overlay-persist-20261022; its Docker context retains the eight manifest hashes. Exact command: cd /tmp/dldws001-overlay-build-20261022 && python3 build_candidate.py. The script reruns all preflight gates, builds with pull disabled and network none, proves image layers, and runs only bounded synthetic final-image tests. It stops on any mismatch or Docker API denial.

Evidence: /tmp/dldws001-overlay-build-20261022/BUILD_EXECUTION.md; evidence/static-build-preflight.json; evidence/docker-access-preflight.json; evidence/overlay-build-result.json. Existing Writer race and full canonical Dockerfile smoke failure remain unresolved. No image was created and no production resource was changed.


## SEPARATE APPROVED EXECUTION — overlay evidence record and read-only deployment preflight

APPROVAL_DATE: 2026-10-22
AUTHORIZATION: Explicit user approval in the DLDWS-001 overlay build success record and deployment preflight request.
CANONICAL_BASE: 10e1e332c3333451c05c16c9181cf88a242d2081
> TASK_ID: DLDWS-001
REQUIRED_WORKSTREAMS: downloader,discovery-writer-safety

This separate execution authorizes (1) recording the operator-supplied overlay build and final UI extraction results with their provenance and limitations, and (2) read-only inspection of the existing CT108 Docker/Compose configuration, backup metadata/integrity evidence, rollback prerequisites, and Writer restart/socket-lifecycle risk. Read the operator evidence if accessible; otherwise label it user-provided and do not claim direct verification. Do not inspect or expose secret values.

### AUTHORIZED_SCOPE
- Record the reported parent image sha256:83322ee82e736b5ba026b8d98d5709b9685ca9c6b051c2a7f4c7b9bf8d058573, overlay image sha256:14f8c831d692db0a0d4f0f3b70eac0ca840b1daf0a66927aebc578eaf6541c4d, tag missav-dlp-web:dldws001-legacy-overlay-persist-20261022, build result, and extracted UI hashes, distinguishing operator-provided evidence from locally read-back evidence and from prior Chromium results.
- Read-only CT108 inspection of the named Compose files, current Downloader image/container, effective topology and dependencies, relevant backup path metadata and existing verification records, and rollback feasibility.
- Append results to both workstream active files and the canonical handoff after inspection; preserve all prior history.

### PROHIBITED_SCOPE
No Docker container/image mutation, build, run, exec, start, stop, restart, recreate, Compose apply, retry/download, production data access beyond read-only metadata specifically listed above, backup extraction/modification, Writer socket cleanup/systemd change, Gluetun/Selkies/Stage11/NAS/Jellyfin changes, product code, contract/router changes, or deployment. No privilege escalation or permission workaround. Do not infer Writer restart safety from unchanged overlay files alone.

### ACCEPTANCE_AND_BOUNDARIES
Record PRODUCTION_DEPLOYMENT=NOT_RUN. If CT108, Docker, Compose, or backup evidence is unavailable, report the relevant gate as INCOMPLETE/BLOCKED without guessing. Keep the known Writer socket race unresolved. A deployment readiness conclusion must account for unverified Writer restart safety and backup recovery; this approval does not authorize deployment.

EXECUTION_STATUS: AUTHORIZED only after this matching block is remotely read back from both workstreams.

## EXECUTION RESULT — overlay evidence record and read-only deployment preflight (2026-10-22)

BUILD_EVIDENCE_RECORDED=PASS
UI_EVIDENCE_RECORDED=PASS
COMPOSE_PREFLIGHT=INCOMPLETE
BACKUP_ACCESS=INCOMPLETE
BACKUP_INTEGRITY=INCOMPLETE
ROLLBACK_PLAN=INCOMPLETE
ROLLBACK_TEST=NOT_RUN
WRITER_RESTART_SAFETY=INCOMPLETE
DEPLOYMENT_READINESS=BLOCKED
PRODUCTION_DEPLOYMENT=NOT_RUN
PRODUCTION_CONTAINER_UNCHANGED=YES for this inspection only; live daemon state could not be read
GITHUB_READBACK=pending

The recorded build result is operator-originated. The evidence directory was accessible and its artifacts were read back locally at /tmp/dldws001-overlay-build-20261022/evidence/operator-build-oylfwt00. image-integrity.json reports PASS, parent image sha256:83322ee82e736b5ba026b8d98d5709b9685ca9c6b051c2a7f4c7b9bf8d058573, new image sha256:14f8c831d692db0a0d4f0f3b70eac0ca840b1daf0a66927aebc578eaf6541c4d, tag missav-dlp-web:dldws001-legacy-overlay-persist-20261022, exactly eight changed runtime files, exact parent layers preserved, and Writer files unchanged. The candidate-image.tar is 342,911,488 bytes with SHA-256 96853b690cc099fe006350b00d45c99249dfe754bbcf02dd73de54db6066f1e4. final-image-tests.json reports 23 synthetic tests, 0 failures/errors, app_imported=false, workers_started=false, production_mounts=false and external_requests=0. These artifacts substantiate the operator run but are not a fresh Docker daemon reproduction.

UI extraction at /tmp/dldws001-final-ui-20261022.Eenyxd was read back. index.html SHA-256 a09930a0dd298e11ec12d891da13cc7a38b1a80a2d1bbb313234ea389dcbad7b and teddy-reliability.js SHA-256 b8204eee2c668c9c1fb8bcd780bd7301a61a0c1b2b5f2f153af7f7c77d698ae9 match both the stated hashes and the final image-runtime assets byte-for-byte. The bulk retry label is present and the Downloader restart label/API markers checked are absent. This is static asset verification; Chromium was not run against the final image. The earlier Chromium 10/10 result remains prior evidence, not a final-image browser run.

Read-only docker info/image inspect/container inspect calls were denied by permission on /var/run/docker.sock in hostname downloader, UID/GID 0:0. No permission change or escalation was attempted. Therefore the current container ID/state/image, live Compose labels, local availability of either image, current max_concurrent value, and live Gluetun/Selkies states remain unverified. No Docker-mutating call was issued.

All four supplied Compose/env paths exist. A read-only docker compose config using the specified file order and gluetun.env resolved successfully: project missav-dlp-web; Downloader service missav-dlp-web declares image missav-dlp-web:stage13-ui-24fc73a, 31 environment keys, 14 mounts, port 58000:5000, group_add 988, the /run/teddy-library-discovery-writer directory as a read-only mount, and depends_on gluetun. Both Selkies services declare dependencies on the Downloader. Secret values were not emitted. This proves the supplied files parse together, not that they are the files currently applied to the live container. The new overlay image is not the image currently named in this resolved configuration. Compose compatibility and live drift comparison remain incomplete.

The Data_5TB backup path /mnt/pve/Data_5TB/dldws001-backups/backup-20261020-110732-TbdQOd/data.tar and mount are absent in this LXC; no archive listing, checksum, extraction or restore was attempted. Earlier user-submitted Proxmox backup/restore results remain historical evidence only and do not establish current accessibility or integrity.

Rollback plan (not executed): if a separately approved deployment later fails, first stop further Downloader actions and capture the then-current task/settings/fragments state; do not run compose down or restore an old backup over changed data. Verify the exact currently running image, original Compose inputs and backup accessibility. If state is safe for the older application, apply an image-only override to the exact verified old image ID and target only missav-dlp-web with dependency handling disabled; leave Writer, Gluetun and Selkies untouched. Then verify Downloader health and the unchanged dependency/socket state. Do not restore data unless a separate comparison proves it is necessary and safe. This plan is INCOMPLETE until the old image is confirmed locally, live Compose identity is verified, backup is accessible, and Writer reconnection risk is resolved.

Writer risk remains unresolved. The parsed Compose contains no Writer service; it only mounts the Writer socket directory read-only. In this LXC, lstat sees a socket path with mode 0660, uid 0 and gid 65534, while Compose adds supplementary GID 988. systemctl queries did not establish Writer unit state and ss showed no matching listener line; neither proves the live Writer state. The known active-socket cleanup race is still unresolved, and no evidence proves restart/reconnection is safe. Do not infer safety from unchanged Writer files in the overlay.

No production container, image, data, backup, Writer, Gluetun, Selkies or Stage11 resource was intentionally changed. The result is blocked for deployment approval because the live Docker state, backup access/integrity, max_concurrent value and Writer restart safety are not verified. The prior build BLOCKED record remains historical; this operator build PASS record supplements it and does not resolve the Writer issue.

Next action: from an authorized Proxmox/CT108 operator session, provide read-only confirmation of the exact live Downloader image/container/Compose labels, Data_5TB archive availability and checksum record, current max_concurrent=4, and Writer listener/service state; then reassess deployment separately.

## SEPARATE APPROVED EXECUTION — Downloader-only overlay deployment

APPROVAL_DATE: 2026-10-22
AUTHORIZATION: Explicit user approval for one production replacement of the missav-dlp-web Downloader container using the verified overlay image, only if every stated safety gate passes.
CANONICAL_BASE: bc238f2ff79a07fa1dcc40133affdde54782bb8d
> TASK_ID: DLDWS-001
> CONTRACT_VERSION: 1.0.0
> REQUIRES_WORKSTREAMS: downloader,discovery-writer-safety

### AUTHORIZED_SCOPE
- Read-only preflight of the exact CT108 container, original four Compose files in their recorded order, environment file, pinned old/new image IDs, download state, max_concurrent, dependencies, Writer socket/unit/listener, and backup evidence.
- If all mandatory gates pass, at most one Compose replacement of the missav-dlp-web service only, with --no-deps --no-build --pull never, and post-deployment read-only checks. If Codex lacks Docker API access, prepare and statically validate a guarded deployment script and a separate rollback script for the operator; do not bypass access controls.
- Roll back the Downloader only once if the approved conditions make it safe. Never restore a backup over changed data automatically.

### FIXED_TARGETS
Old image: sha256:83322ee82e736b5ba026b8d98d5709b9685ca9c6b051c2a7f4c7b9bf8d058573
New image: sha256:14f8c831d692db0a0d4f0f3b70eac0ca840b1daf0a66927aebc578eaf6541c4d
New tag: missav-dlp-web:dldws001-legacy-overlay-persist-20261022
Compose project/service: missav-dlp-web / missav-dlp-web

### PROHIBITED_SCOPE
No Writer, Gluetun or Selkies restart/recreation; no download/retry, task or parts mutation, settings change, data cleanup, backup restore, image build/pull/delete/prune, Compose source modification, Stage11/NAS/Jellyfin work, or privilege escalation. The unresolved Writer socket cleanup race remains a hard gate; do not infer safety from unchanged Writer files.

### MANDATORY_GATES
Fail closed if exact image/container IDs or status differ; Compose file order, project/service, or image-only diff is not exact; max_concurrent is not 4; running/queued/MP4 work or automatic retry risk exists; tasks/fragments cannot be verified preserved; Writer socket listener/systemd socket is not healthy; Gluetun/Selkies status is unknown; old image is unavailable; the backup file and SHA-256 cannot be matched; or overlay image integrity is not verified. Do not stop work or alter settings to make a gate pass.

### ACCEPTANCE_AND_BOUNDARIES
Deployment is authorized only after all mandatory gates pass. If Docker API access is denied, no deployment call is permitted; provide the guarded scripts and exact operator command. Preserve historical BLOCKED records. Keep Writer safety status separate from Downloader feature validation.

EXECUTION_STATUS: AUTHORIZED only after this matching approval block is remotely read back from both workstreams.

## EXECUTION RESULT — Downloader-only deployment (2026-10-22)

DEPLOYMENT_PREFLIGHT=BLOCKED
PRODUCTION_DEPLOYMENT=NOT_RUN
LIVE_IMAGE_ID=UNKNOWN (Docker inspect was denied by /var/run/docker.sock permissions)
COMPOSE_PRESERVED=YES (the four recorded source files and environment file were unchanged; read-only Compose parsing and the image-only model comparison passed; comparison to the live container remains unavailable)
DOWNLOAD_DATA_PRESERVED=INCOMPLETE (read-only state matched the recorded baseline: max_concurrent=4; four failed ENOSPC jobs at retry limit 30; four .parts directories, 8,637 fragments and 16,996,662,891 bytes. No deployment or data write occurred.)
WRITER_UNCHANGED=INCOMPLETE (no Writer lifecycle operation was issued; systemd and listener state could not be read. The observed socket path was mode 0660, uid 0, gid 65534; the required client GID 988 access was not proven.)
GLUETUN_SELKIES_UNCHANGED=YES (no lifecycle operation was issued; live IDs/status could not be independently inspected)
LOGIN_UI_API=INCOMPLETE
NO_SUBMISSION_WINDOW=NOT_CONFIRMED (the scripts require explicit operator acknowledgement but do not disable admission)
ROLLBACK_READY=NO (guarded script prepared; live image/config/data, backup and Writer gates are not established)
ROLLBACK_EXECUTED=NO
WRITER_SAFETY_ISSUE=UNRESOLVED

The candidate scripts are isolated under `/tmp/dldws001-downloader-deploy-20261022`: deploy.py SHA-256 `cb91439a1ff1eb390628224ba71f7bafe3baaff32d86a35bf5dd0f901f9d9d32`; rollback.py SHA-256 `ed481ef0609683007b9850c79f2eb822bdfaaf5cf65a80ece117412cb0055078`. Both passed Python syntax compilation and static command review; neither was executed. The only Compose lifecycle calls in those scripts are one service-targeted `up` per script, with `--no-deps --pull never --no-build`. No stop/down/restart/run/exec/prune or privilege escalation is present.

Blocking evidence: Docker API access is denied; the Data_5TB mount and `data.tar` are absent in this LXC and the archive SHA-256 is not available in the recorded handoff; systemd Writer state and a matching socket listener are not readable; the MP4 lock holder cannot be established in this environment. Historical operator build/image/UI evidence remains provenance-labeled and does not resolve these live gates.

PRODUCTION_CONTAINER_CHANGED_BY_THIS_EXECUTION=NO

Next action: from the authorized CT108/Proxmox operator environment, collect current read-only Docker/image/container and dependency state, the mounted backup archive SHA-256 plus source-manifest path, and Writer socket/unit/listener/client-GID evidence. Rerun no lifecycle command unless all gates then pass.


## SEPARATE APPROVED EXECUTION — Downloader deployment backup evidence gate correction (2026-10-22)

APPROVAL_DATE: 2026-10-22
AUTHORIZATION: Explicit user approval for isolated review and minimum modification of the Downloader deploy/rollback scripts’ backup-evidence verification path, with synthetic offline validation only.
CANONICAL_BASE: beff9da5480e4581c9816855f51d02975d5e6755
> TASK_ID: DLDWS-001
> CONTRACT_VERSION: 1.0.0
> REQUIRES_WORKSTREAMS: downloader,discovery-writer-safety

### AUTHORIZED_SCOPE
- Preserve the original scripts and work only in a fresh isolated copy.
- Inspect the existing backup gate, state-file contract, manifest role, and deploy/rollback call boundaries.
- If the actual source-manifest identity and a trusted Proxmox-to-CT108 evidence path can be established, make only the minimum backup-evidence verifier change and run synthetic offline tests for valid evidence and tamper/replay/path rejection. Keep every other deployment and rollback gate unchanged.
- If manifest provenance or attestation trust cannot be established, fail closed and document the blocker without claiming a passing gate.
- Record the result and provenance in this file and the canonical handoff.

### PROHIBITED_SCOPE
No production deployment, rollback execution, Docker image/product-code change, image/container lifecycle action, data or settings change, Writer/Gluetun/Selkies change, download/retry, backup creation/restoration, Stage11/NAS/Jellyfin change, contract/router edit, or permission workaround. Do not weaken or bypass any existing safety gate. The known Writer socket cleanup race remains UNRESOLVED.

EXECUTION_STATUS: AUTHORIZED only after matching approval readback from both workstreams. This approval does not make the deployment or rollback gates PASS and authorizes no lifecycle command.


## EXECUTION RESULT — DLDWS-001 backup-evidence gate minimum-change review (2026-10-22)

BACKUP_GATE_DESIGN=INCOMPLETE (blocked before verifier modification because the source-manifest file path/role and trusted Proxmox-to-CT108 attestation root were not established).
PVE_ATTESTATION=NOT_RUN.
SOURCE_MANIFEST_VERIFIED=NOT_RUN (the recorded digest exists, but the actual source-manifest file and its role were not identified).
CT108_EVIDENCE_VALIDATION=INCOMPLETE.
TAMPER_REJECTION=INCOMPLETE (no new verifier was implemented; no unsigned JSON was treated as trusted).
EXISTING_SAFETY_GATES_PRESERVED=YES (deployment and rollback scripts were copied unchanged; no guard or lifecycle path was edited).
DEPLOY_SCRIPT_STATIC_TEST=PASS (read-only AST syntax parse of isolated copy only; backup-attestation behavior was not tested).
ROLLBACK_SCRIPT_STATIC_TEST=PASS (read-only AST syntax parse of isolated copy only; backup-attestation behavior was not tested).
PRODUCTION_DEPLOYMENT=NOT_RUN.
ROLLBACK_EXECUTED=NO.
WRITER_SAFETY_ISSUE=UNRESOLVED.

The isolated review copy is /tmp/dldws001-backup-attestation-20261022. Original /tmp/dldws001-downloader-deploy-20261022/deploy.py and rollback.py remain unchanged at SHA-256 cb91439a1ff1eb390628224ba71f7bafe3baaff32d86a35bf5dd0f901f9d9d32 and ed481ef0609683007b9850c79f2eb822bdfaaf5cf65a80ece117412cb0055078. The copied files have the same hashes. No deployment state file was created.

The existing deploy.py:backup_gate() requires DLDWS_SOURCE_MANIFEST_FILE, hashes that local file against 252491423da01d4f1eeabad3e7caeaeac3e8cb23b2eb46818aba91b7be178d16, then assumes /mnt/pve/Data_5TB and the archive are mounted inside CT108. rollback.py:current_download_state() calls the same gate and compares its two-digest result to the saved deployment state. The current state schema stores archive and source-manifest hashes only. Existing Compose, task, fragment, MP4, Writer, dependency, quiet-window, one-shot and service-only protections were not changed.

The exact source-manifest path and meaning are absent from the available original scripts, deployment evidence, and canonical handoff. The known /tmp/dldws001-overlay-build-20261022/manifest.json hashes to a2b5c134528aea387fc93fd8d25c56e88c5c1a47c6408562536dd4fd9ab60b7f and has overlay fields (before, after, canonical_sha, feature_commit, parent_image_id); it is a different Docker overlay manifest and was not substituted for the backup source manifest. This CT108 session has no /mnt/pve/Data_5TB mount and did not access pve.

No authenticated PVE attestation key, pinned trust anchor, challenge/nonce exchange, or evidence-transfer mechanism is established. A plain JSON document or operator-set PASS/hash environment variable would be forgeable and is not an acceptable gate. Therefore no backup-verifier code change or synthetic verifier test was started; the explicit missing-manifest precondition requires BLOCKED. No PVE backup result is claimed by Codex.

NEXT: From the original Proxmox backup-generation records, identify the exact source-manifest path and its role, and establish an independently verifiable PVE signing/trust-anchor and one-time challenge delivery path before authorizing a verifier change.


## MANIFEST ROLE CLARIFICATION — DLDWS-001 backup evidence review (2026-10-22)

A broader read-only search found /tmp/dldws001-integration-20261019/evidence/source-manifest.json (102,407 bytes; SHA-256 313213a9bed9aacf41c5b3bc55dc7c3b86875def387886c57605f2a989cd44c0). Its top-level keys are build_result, dl001_context, dws001_b, final_candidate_files, integration_changes, integration_root, notes, and offline_results. This is integration-candidate provenance, not the Proxmox backup source manifest: its digest does not match the required 252491423da01d4f1eeabad3e7caeaeac3e8cb23b2eb46818aba91b7be178d16. The separate overlay manifest remains a third, distinct artifact at SHA-256 a2b5c134528aea387fc93fd8d25c56e88c5c1a47c6408562536dd4fd9ab60b7f. No file path/role for the required backup source manifest was established; all blocked gates and conclusions remain unchanged.

## SEPARATE APPROVED EXECUTION — UI alignment overlay build and Downloader-only production deployment (2026-10-22)

APPROVAL_DATE: 2026-10-22
AUTHORIZATION: Explicit user approval for one overlay image build from the isolated UI-alignment candidate and, only if every production safety gate passes, replacement of the Downloader container only.
> TASK_ID: DLDWS-001
> STATUS: IN_PROGRESS
> CONTRACT_VERSION: 1.0.0
> REQUIRES_WORKSTREAMS: downloader,discovery-writer-safety
CANONICAL_BASE: teddy-subtitle-stage11 at 0352f6785b0dc978f29b4aeace8980fba4ad4cf1
AFFECTED_WORKSTREAMS: downloader,discovery-writer-safety
PRODUCTION_TARGET: missav-dlp-web Downloader container only

### AUTHORIZED_SCOPE
- Use only /tmp/dldws001-ui-alignment-20261022/templates/index.html with SHA-256 4d379e37c76e25781ea4eda8d169af5f24d70a4d53ef74808dc088c37b85766f as the sole overlay file.
- Build one new overlay image using parent image sha256:14f8c831d692db0a0d4f0f3b70eac0ca840b1daf0a66927aebc578eaf6541c4d; verify image identity and integrity before considering deployment.
- If all current production safety gates pass, replace the Downloader container only, using the existing four Compose files and Gluetun environment file without changing their contents.
- Preserve the existing image, job records, downloaded fragments, and all existing data.
- Keep Writer, Gluetun, and Selkies services unchanged and do not restart or modify them.
- Keep the existing Writer safety defect UNRESOLVED.

### PROHIBITED_SCOPE
No real bulk retry or new download; no data cleanup or modification; no Writer/Gluetun/Selkies restart or change; no Stage11, NAS, or Jellyfin change; no Compose/environment-file edits; no additional image build or deployment attempt beyond this one approved image and one Downloader replacement; no weakening of any preflight or rollback safety gate.

THIS CODEX EXECUTION: approval registration and remote readback only. Docker build, product-code edit, and production deployment/restart are NOT AUTHORIZED IN THIS EXECUTION.

## SEPARATE APPROVED EXECUTION — one-time operational MP4 recovery from retained fragments (2026-10-22)

APPROVAL_DATE: 2026-10-22
AUTHORIZATION: Explicit user approval for a one-time, operator-run recovery of four MP4 files from the already retained and verified TS/HLS fragments; Codex may inspect runtime safety rules and prepare an isolated recovery tool and synthetic tests only.
> TASK_ID: DLDWS-001
> STATUS: IN_PROGRESS
> CONTRACT_VERSION: 1.0.0
> REQUIRES_WORKSTREAMS: downloader,discovery-writer-safety
CANONICAL_BASE: teddy-subtitle-stage11 at 5c73d284f7c3203f966e07d0d554982f0f98e8d7
AFFECTED_WORKSTREAMS: downloader,discovery-writer-safety
PRODUCTION_IMAGE: sha256:7200290e8af11d9f253a5efd028bf3be2a2757af9049f0bb9e43bd04f821f2d8
RECOVERY_TARGETS: four existing ERROR jobs whose named TS and verified HLS fragment sets are present

### AUTHORIZED_SCOPE
- Inspect the actual deployed runtime files and current MP4 locking, space reservation, and validation rules; do not infer runtime behavior from GitHub source alone.
- Prepare an isolated one-time recovery utility under /tmp/dldws001-mp4-recovery-20261022/ with separate read-only preflight and explicit execution modes.
- Use only the four already verified filelists and retained fragments; create and validate one new temporary MP4 at a time using stream copy.
- Preserve source TS files, HLS fragment directories, filelists, and task records. Finalize only a validated MP4 when its destination is absent, using atomic no-clobber semantics.
- If the existing MP4 serialization lock cannot be shared, active downloads/MP4 work cannot be excluded, or current reserved-space checks cannot be proven, stop without creating output.
- Do not mark application tasks complete unless an existing safe state-update path is identified; report any required state reconciliation separately.
- The actual production recovery command is to be run by the user from root@downloader. Codex must not execute against production.

### PROHIBITED_SCOPE
No source-fragment, filelist, task-record, or existing-output deletion/overwrite; no new download or retry; no disabling or weakening MP4 safety, locks, or storage reservations; no Docker build/deployment/restart; no Writer, Gluetun, Selkies, Stage11, NAS, or Jellyfin change. The existing Writer safety defect remains UNRESOLVED. This approval is distinct from the prior image build/deployment approval and authorizes no container lifecycle action.

THIS CODEX EXECUTION: approval recording/readback, runtime safety analysis, isolated recovery-tool implementation, and offline synthetic tests only. No production preflight execution that mutates state, no MP4 generation in /downloads, and no production task-state change.


## SEPARATE APPROVED EXECUTION — legacy HLS MP4 recovery compatibility mode (2026-10-22)

APPROVAL_DATE: 2026-10-22
AUTHORIZATION: Explicit user approval for an isolated legacy recovery mode, synthetic validation, and operator-ready CT108 commands within the previously approved one-time recovery of four MP4s.
> TASK_ID: DLDWS-001
> STATUS: IN_PROGRESS
> CONTRACT_VERSION: 1.0.0
> REQUIRES_WORKSTREAMS: downloader,discovery-writer-safety
CANONICAL_BASE: teddy-subtitle-stage11 at d76982afc705087096721f568b361b0d3fd2c861
PRODUCTION_IMAGE: sha256:7200290e8af11d9f253a5efd028bf3be2a2757af9049f0bb9e43bd04f821f2d8

### AUTHORIZED_SCOPE
- Prepare a separate isolated copy of the existing one-time MP4 recovery candidate with an explicit legacy-evidence mode. Preserve the existing manifest-backed mode and its validation unchanged.
- For legacy jobs, validate task UUID and ERROR state, the UUID-derived .parts directory, explicit source TS mapping, existing filelist order, contiguous zero-based fragment indices, regular non-symlink files, sizes, and contemporaneous SHA-256 values; validate source media streams and duration.
- State clearly that current SHA-256 values establish only the present inspection baseline and later non-change checks, not download-time provenance. Never create or write a synthetic resume-plan.json or fake task metadata.
- Preserve the existing runtime's per-task claim locks, global RemuxTransaction MP4 lock, storage reservation/free-space/inode checks, active-work exclusion, source rechecks, and atomic no-clobber finalization.
- Prepare synthetic tests for valid legacy input and rejection of missing/changed fragments, filelist mismatch, active locks/work, insufficient capacity, task-state changes, symlinks, destination collisions, FFmpeg failure, and stop-after-partial-success.
- Provide exact operator commands for target auto-mapping, read-only preflight, preflight-gated explicit execution, and post-run read-only verification on CT108.

### PROHIBITED_SCOPE
No production recovery execution by Codex; no production MP4 generation during tests; no changes to task records, source TS/fragments/filelists, or existing outputs; no downloads/retries, Docker lifecycle/build/deployment, Writer/Gluetun/Selkies/Stage11/NAS/Jellyfin changes, or weakening of existing safety checks. Only synthetic fixtures may be changed.

### ACCEPTANCE_CRITERIA
- Legacy mode is separate and opt-in; normal manifest validation is not relaxed.
- The legacy evidence limitation is explicit and current hashes are not represented as historical provenance.
- All required synthetic scenarios pass, including preserving source/task bytes and stopping after a later item fails.
- Operator commands derive targets from read-only task state and require a successful fresh preflight artifact before execution; any runtime identity, lock, work-state, storage, or provenance precondition not verifiable on CT108 fails closed.
- Codex performs no operation against /downloads and no production recovery.

## EXECUTION RESULT — legacy HLS MP4 recovery mode (2026-10-22)

LEGACY_MODE=PASS_SYNTHETIC
CANDIDATE=/tmp/dldws001-mp4-recovery-legacy-20261022
RECOVERY_TOOL_SHA256=8cc90a8247da0320c9269acf519331748b5f4ddd18685977f2f3dea33f95e5ff
RUN_WRAPPER_SHA256=5a686162cfc903459620042acd39ecab40641df7ce90421069461b27875b811b
TESTS=PASS; Python 3.10.22 suite 35/35 and wrapper mock guards 3/3
STATIC_CHECKS=PASS; Python compile, shell syntax, and help
PRODUCTION_PREFLIGHT=NOT_RUN
PRODUCTION_RECOVERY=NOT_RUN
PRODUCTION_CHANGES_BY_CODEX=NONE
REAL_FFMPEG_MEDIA_CHECK=NOT_RUN; ffmpeg/ffprobe unavailable in Codex environment
LIVE_IMAGE_AND_RUNTIME=NOT_RUN; CT108 wrapper/tool must match the pinned image and all five runtime fingerprints or fail closed
WRITER_SAFETY_ISSUE=UNRESOLVED
CANONICAL_PRODUCT_CODE_PUBLISHED=NO

The explicit legacy mode preserves strict manifest-mode validation. Its source/fragment SHA-256 values are inspection-time baselines only, not download-time provenance. It keeps the existing task claim, global RemuxTransaction lock, free-space/inode reservation, active-work checks, and atomic no-clobber publication. All synthetic tests use fake media runners; no /downloads path or production FFmpeg was used.

Operator sequence (only after copying the pinned tool and wrapper to CT108 and verifying both hashes):
1. `./run-on-downloader.sh preflight --evidence-mode legacy --auto-targets`
2. Only after JSON `result=PREFLIGHT_PASS`, review the four exact mappings and pass its `preflight_id` once to `./run-on-downloader.sh execute --evidence-mode legacy --auto-targets --preflight-id '<PREFLIGHT_ID>' --confirm DLDWS-001-MP4-RECOVERY-20261022`.
3. Only after `RECOVERY_COMPLETE`, run `./run-on-downloader.sh postcheck --evidence-mode legacy --auto-targets --preflight-id '<PREFLIGHT_ID>'`.

The detailed gates and full commands are in the isolated candidate README. No retry, new preflight workaround, or source/task mutation is authorized if a gate fails.


## EXECUTION RESULT — DLDWS-001 legacy MP4 automatic mapping correction (2026-10-22)

This is a follow-up bug fix within the already approved one-time legacy MP4 recovery scope. It covered isolated candidate changes and synthetic tests only; no production recovery was run.

- MAPPING_FIX=PASS. A 60-character title ending in a space before `.ts` is preserved and accepted while path separators, control characters, malformed legacy names, symlinks, and duplicate media IDs remain rejected. Four failed task UUIDs are mapped by URL media ID, UUID parts folder, recorded error path, and `filename` when present. A fifth top-level TS is excluded only when it has a unique safe ID and conflicts with none of the four targets; it is left untouched.
- FULL_PREFLIGHT_TEST=PASS. The observed-shape synthetic fixture ran the complete legacy `build_preflight` path with four targets, the trailing-space title, and an unrelated fifth TS.
- SAFETY_REGRESSION=PASS. Python 3.10.22 suite 43/43 and wrapper mock 3/3 passed. Coverage retains duplicate/ambiguous IDs, unsafe names, error-path mismatch/traversal, filename mismatch, symlink, missing/tampered fragments and filelists, active locks, space/inode shortage, destination collision, FFmpeg failure, and partial-stop checks. Strict manifest mode and shared MP4 locks, task claims, reservations, no-clobber publication, and source/task preservation were not changed.
- Candidate: `/tmp/dldws001-mp4-recovery-legacy-20261022`; evidence: `evidence/mapping-fix-20261022/`.
- `recover_mp4.py` SHA-256: `e77fb6b6903ffac93440f8c3512641b095c141757884e4c51fc50ac9171f43d9`.
- `run-on-downloader.sh` SHA-256: `afc7f260a9dc146fb7fef5b2e581c0b17d526334cfa71ad59cee792ad887cad9`; its pinned tool SHA matches the script above.
- PRODUCTION_UNCHANGED=YES; Codex did not access operational download data or run CT108 preflight, execute, or postcheck. No MP4 was created. Docker, container, service, Writer, and task data were not changed. Writer safety remains UNRESOLVED.
- Canonical product code was not changed or published. CT108 operator action remains: transfer the two pinned files, verify both hashes, run the documented legacy preflight, and proceed only if it returns `PREFLIGHT_PASS` with the expected four mappings.


## EXECUTION RESULT — DLDWS-001 legacy MP4 status truncation compatibility (2026-10-22)

AUTHORIZATION: Follow-up bug fix within the existing approved one-time legacy MP4 recovery. Isolated tool changes and synthetic validation only; no new design or production execution was introduced.

- ERROR_PATH_FIX=PASS. The pinned runtime snapshot `parent-image-files/teddy_entrypoint.py` records `status = prefix + str(exc)[:100]` and `last_error_detail = str(exc)[:1000]`. The test exercises the exact extracted recording assignments with a fake core. This source check is not a new live CT108 inspection.
- Only a known runtime status prefix, consistent error kind, and exact message equality with `last_error_detail[:100]` permit the truncated duplicate status to defer to the full detailed record. The detailed record must contain a complete target-validated path. Contradictory status/detail, wrong cut length, missing/incomplete detail, the potentially clipped 1,000-character detail limit, unknown status formats, and unsafe other error fields remain blocked.
- FULL_PREFLIGHT_TEST=PASS_SYNTHETIC. A single synthetic fixture includes four failed UUID targets, status lengths 105/111/117 characters, full detailed errors, Korean filenames, a 60-character title ending in a space, and the unrelated fifth TS. It completes legacy preflight without changing source/task bytes; the fifth TS stays untouched.
- SAFETY_REGRESSION=PASS. Python 3.10.22 recovery suite 78/78 and wrapper mock 3/3 passed. The same fixture also runs existing active-lock, storage/inode, source-change, symlink, filelist, no-clobber, FFmpeg-failure, partial-stop, mock-execute, and postcheck cases. The original manifest-mode tests remain included and PASS.
- Existing functions other than `_legacy_error_path_values` are AST-identical to the prior candidate; `_legacy_status_duplicates_full_detail` is the only added tool function. Global MP4/task locks, space reservation, no-clobber publication, manifest-mode validation, and the four-of-five TS mapping are unchanged.
- Candidate: `/tmp/dldws001-mp4-recovery-legacy-20261022`. Evidence: `evidence/status-truncation-20261022-xi1bi5vx/`, including the preserved pre-fix failure, before snapshots, final tests, static checks, and code diffs.
- `recover_mp4.py` SHA-256: `fe6a7ef2fa31737aa459969be87fd607feaeaf004dc1c1eb54fd4dec576df563`.
- `run-on-downloader.sh` SHA-256: `55b1c2066a90035bf7fc3397df794dd97f61660e7d0e2df475dc8cc778ff74c3`. Its pinned tool SHA and the README verification commands match these artifacts.
- PRODUCTION_UNCHANGED=YES. Codex ran no operational preflight, MP4 generation/recovery, download, Docker lifecycle/build/deployment, or operational data/service change. Media tests use fake runners and synthetic data only. Writer safety remains UNRESOLVED; canonical product code was not published.

Operator next action remains the approved CT108 sequence in the candidate README: verify the two updated hashes, run legacy automatic-target preflight, review its four mappings, and execute only after a fresh `PREFLIGHT_PASS`; postcheck follows successful completion. Synthetic PASS does not claim operational preflight or recovery PASS.


## EXECUTION RESULT — DLDWS-001 legacy MP4 duration mismatch review (2026-10-22)

AUTHORIZATION: User-approved isolated failure analysis, legacy-only validation design/candidate and synthetic tests. No operational preflight/execute retry is authorized; prior failed receipt must not be reused.

- DURATION_ROOT_CAUSE=PARTIALLY_CONFIRMED. `_validate_one_legacy` stores retained-TS ffprobe duration; both execute and postcheck pass it to `_validate_output`. Its max(5 seconds, 2%) comparison runs before full output decode. Operator evidence is TS=4644.021334 seconds and concat stream-copy null out_time=9092.295789 seconds, exit 0; actual temporary MP4 duration is unknown. Partial TS versus HLS timestamp discontinuity remains INCOMPLETE. No out_time was treated as complete media duration.
- VALIDATION_DESIGN=BLOCKED_FOR_EXECUTABLE_INTEGRATION. A conservative isolated model compares independently decoded HLS/MP4 stream content, counts and normalized rational timelines; it rejects gaps/resets/overlaps, missing streams, changed content, early EOF and A/V offset changes. It is not a media collector, not a trusted JSON proof interface, and is NOT connected to recovery execution. A bounded collector, codec/audio-framing/time-base handling and actual synthetic TS/H.264/AAC/MP4 evidence remain unverified. Existing duration checks were not removed or widened.
- SYNTHETIC_TESTS=PASS_SCOPED: Python 3.10 model 12/12 and existing recovery regression 78/78. Existing manifest, fragment mutation/missing, locks, reservation, no-clobber, packet failure, partial-stop and postcheck tests pass with fake media runners. REAL_MEDIA_VALIDATION=NOT_RUN. Full ffmpeg/ffprobe unavailable; existing Playwright ffmpeg lacks required media support. This is not an operational recovery PASS.
- Candidate/evidence: `/tmp/dldws001-mp4-duration-review-20261022/` (`ANALYSIS.md`, `validation_model.py`, `test_validation_model.py`, `model-tests.txt`, `existing-regression.txt`). Existing recover_mp4.py remains SHA-256 `fe6a7ef2fa31737aa459969be87fd607feaeaf004dc1c1eb54fd4dec576df563`; wrapper remains `55b1c2066a90035bf7fc3397df794dd97f61660e7d0e2df475dc8cc778ff74c3`.
- ORIGINAL_SAFETY=UNCHANGED; PRODUCTION_UNCHANGED=YES; RETRY_AUTHORIZATION_REQUIRED=YES. No production preflight/execute/postcheck, media creation, source/task edit, Docker/service operation or canonical product-code publication. Writer safety remains UNRESOLVED.
- Required operational read-only evidence remains NOT_RUN: failed receipt and used/result sidecars; committed-output status; owned temporary-directory residue; FFmpeg child processes; existing MP4/task lock holders; storage reservations; original-file preservation and available space. Code cleanup paths do not prove actual cleanup. Do not delete receipts/locks/reservations or use mutating runtime helpers for inspection.

NEXT: establish and verify the independent media-evidence collector in an isolated capable environment before an executable patch. No retry or new preflight workaround is authorized by these test results; separate explicit operational retry approval and cleanup evidence are required.


## SEPARATE APPROVED EXECUTION — real FFmpeg HLS/MP4 equivalence validation (2026-10-22)

> TASK_ID: DLDWS-001
> STATUS: IN_PROGRESS
> CONTRACT_VERSION: 1.0.0
> REQUIRES_WORKSTREAMS: downloader,discovery-writer-safety

User authorizes preparing an isolated functioning FFmpeg/ffprobe environment, generating real synthetic H.264/AAC TS fragments and MP4, validating content/count/timeline/full-decode equivalence with bounded resources, and preparing a legacy-only recovery patch candidate only after real-media tests pass. Preserve manifest-mode behavior, all original locks/reservations/no-clobber/input rechecks, existing candidates/evidence and source data. Provide separate CT108 read-only evidence and failed-run residual/lock/reservation/receipt inspection procedures. No CT108 preflight/execute retry, old receipt reuse, operational MP4 creation, source/task mutation, Docker lifecycle/build/deployment, Writer/Stage11/NAS or other-service change is authorized. Isolated test success is not retry authorization or operational recovery PASS.


## EXECUTION RESULT — real FFmpeg HLS/MP4 equivalence validator (2026-10-22)

> TASK_ID: DLDWS-001; CONTRACT_VERSION: 1.0.0; REQUIRES_WORKSTREAMS: downloader,discovery-writer-safety. This is the authorized isolated media-validation follow-up. It authorizes no operational recovery retry or receipt reuse.

- REAL_FFMPEG_TEST=PASS. FFmpeg and ffprobe 7.1.5-0+deb13u1 were extracted under `/tmp/dldws001-real-media-20261022/sysroot/` from official Debian packages with signed-index/package SHA verification; no system installation, production image or runtime environment change. Obsolete-index/package download failures and corrected tool preparation provenance remain in evidence.
- INPUT_OUTPUT_EQUIVALENCE=PASS_TESTED_FORMATS. Eighteen actual generated H.264/yuv420p + AAC scenarios passed (48kHz mono; 44.1/48kHz stereo). The bounded validator compares full decoded video/audio content, frame/PCM byte-sample quantities, packet counts, normalized timelines, A/V relative start, output decoded span/container duration and full decode success. The retained TS duration and progress out_time are not output-completeness references. Partial retained TS with complete HLS is a tested success; missing/duplicate segments, changed video/audio, shifted A/V, early EOF and truncated output are tested rejections.
- TIMELINE_DISCONTINUITY_TEST=PASS. B-frame presentation reordering, an identical common origin shift and validated per-fragment reset/concat boundary padding do not automatically fail. Concat boundary metadata distinguishes these from internal DTS gap/reset/backwards behavior, which remains blocked. Decoded relative timelines must match exactly; only actual MP4 movie-time quantization plus single stream ticks accounts for A/V origin rounding. No broad duration tolerance was added.
- RECOVERY_PATCH_READY=PASS_ISOLATED_CANDIDATE_ONLY. `/tmp/dldws001-mp4-recovery-media-20261022/` embeds the validated collector into a single streamed tool. Legacy preflight binds HLS reference evidence in receipt schema 2; execute and postcheck independently validate output against it. Existing manifest validators, original `_validate_output`, source checks, shared MP4/task locks, space/inode checks/reservations and no-clobber helpers are AST-unchanged. The original transaction/publication flow remains; validator selection changes for legacy only.
- Additional actual-media integration completed four sequential synthetic ERROR-job MP4s and postcheck, preserving Korean/trailing-space names and an unrelated fifth TS. A separate short-output run failed before publication, preserved sources/tasks, cleaned its own temp, released locks/reservations and rejected receipt replay; postcheck rejected output mutation. Five integration assertions passed. Existing mocked gate suite 78/78 and static/read-only tests 7/7 also passed; mocked media boundaries are explicitly distinguished from real media tests.
- Resource boundary: incremental 32KiB record parsing, 64KiB stream metadata, 1MiB hashing chunks, capped 100,000-fragment identity sets, no full packet/frame logs, 2GiB per-media-child address space, bounded execution and owned child-process cleanup. FFmpeg decoding uses one codec thread. Unsupported codec/stream/pixel/timebase/framing or uncertain continuity fails closed. Actual CT108 inputs and broader media formats remain unverified; equivalence to retained fragments does not establish historical download completeness.
- CT108_EVIDENCE_REQUIRED=YES_NOT_RUN. `/tmp/dldws001-real-media-20261022/collect_ct108_readonly.py` provides inventory and optional `--scan-media` procedures using only existing container tools and fixed image/container identity. It writes reports to stdout and never calls recovery preflight/execute/postcheck, creates MP4/receipt/lock/reservation, or starts workers. Real generated-media fixture testing confirms all four read-only scans and original-byte preservation.
- FAILED_EXECUTION_CLEANUP_CHECK=PREPARED_OPERATIONAL_NOT_RUN. Inventory covers old receipt/used/result status, committed/final-output presence, owned temp metadata, existing lock/reservation observations and media processes. Kernel lock visibility is namespace-limited; absence is not a lock-release proof. No residual data is deleted. Actual operational cleanup and TS-partial-versus-HLS-timeline diagnosis remain UNKNOWN pending operator evidence.
- New tool SHA-256: `27b8d181b8201c50ccc876b7d9652ce6b33adb63039468643c5347b732fd9528`; blocked wrapper SHA-256: `abfe7c334f0dd44d78fabf0ccda2231642d2878d4c6323799d659a45df618200`. Standalone validator SHA-256: `de4a5dc3a42edf761ed2ef89bc6c1177f07645914ab6fd0e50c38ad80b15fd5f`; read-only collector SHA-256: `abc60b4634417342b42eeb07e9125b67691646271c5fd4c61109a8f459f734c4`.
- Evidence and exact operator read-only commands: `/tmp/dldws001-real-media-20261022/README.md`, `SHA256SUMS`, `evidence/real-media-results.json`, `real-recovery-integration.json`, `ast-safety-comparison.json`, `static-readonly-final7.log`, `readonly-final-focused.log` and tool provenance logs. Original analysis/recovery candidates and failed-run evidence are preserved.
- PRODUCTION_UNCHANGED=YES; PRODUCTION_PREFLIGHT/EXECUTE/POSTCHECK=NOT_RUN; CANONICAL_PRODUCT_CODE=NOT_PUBLISHED; WRITER_SAFETY_ISSUE=UNRESOLVED. The candidate operational wrapper/CLI and `/downloads` execute are explicitly blocked. Synthetic success is not operational retry approval; the old preflight ID is never reusable.

NEXT: operator collects the documented CT108 read-only inventory and media evidence, including failed-run cleanup state. Actual recovery retry requires a separate explicit approval and review of that evidence before any operational guard is released.


## CROSS-WORKSTREAM RECORD — GANA-3223 HLS post-processing follow-up (2026-10-22)

> TASK_ID: DLDWS-001
> STATUS: IN_PROGRESS
> CONTRACT_VERSION: 1.0.0
> REQUIRES_WORKSTREAMS: downloader,discovery-writer-safety

This entry records the shared DLDWS-001 approval for traceability only. The approved HLS local-result collection fix belongs to the Downloader workstream; this workstream contract explicitly excludes MP4 conversion and download processing. No Discovery Writer Safety product code, tests, services, sockets, databases, or operational state are in scope or authorized to change. The unresolved Writer socket issue and its existing evidence remain untouched. Production deployment and all Downloader operational actions remain unauthorized.



## COORDINATION RESULT — DLDWS-001 GANA-3223 HLS post-processing follow-up (2026-10-22)

The approved HLS post-processing correction was implemented and tested only in an isolated Downloader candidate. This workstream's contract excludes MP4/download processing; no Discovery Writer Safety product code, tests, service, socket, database, or operational state was changed. The existing Writer socket safety issue and all prior evidence remain unresolved and untouched. Production deployment, downloads, and task-state changes were not performed. Candidate result and hashes are recorded in the Downloader ACTIVE_WORK and canonical handoff.


## SEPARATE APPROVED EXECUTION — GANA-3223 HLS result fix overlay build and Downloader-only deployment (2026-10-22)

> TASK_ID: DLDWS-001
> STATUS: IN_PROGRESS
> CONTRACT_VERSION: 1.0.0
> REQUIRES_WORKSTREAMS: downloader,discovery-writer-safety
AUTHORIZATION: Explicit user approval dated 2026-10-22; authorization-time canonical HEAD cabec2a9ca8f9578f6009f051183f12d1a33386d.

AUTHORIZED_SCOPE:
- Verify the actual current Docker engine, running Downloader identity, image/runtime fingerprints, existing Compose configuration, backups, data, active-work and rollback conditions read-only.
- Build one isolated minimal overlay using exact parent image sha256:7200290e8af11d9f253a5efd028bf3be2a2757af9049f0bb9e43bd04f821f2d8. Replace only /app/teddy_mp4_queue.py with the approved candidate SHA-256 593b3ad77f50e2af64589d84a005fad5ce79495e4280011f3e240a6961ba9730 from /tmp/dldws001-gana3223-hls-result-fix-20261022/.
- Validate the final image's HLS/yt-dlp result handling, unchanged runtime files and existing safety protections using isolated synthetic tests.
- Only if every current protection gate passes, replace the missav-dlp-web service alone using the verified existing Compose/image-only procedure; preserve all other settings, dependencies, data and old image. Safe Downloader-only rollback is authorized if required and data compatibility is established.
- Record actual outcomes in both ACTIVE_WORK files and CURRENT_HANDOFF.md with remote readback. Prepare /tmp/TEDDY_DOWNLOADER_UNIFIED_NEXT_CHAT_HANDOFF_20261022_AFTER_DEPLOY.md for the next conversation.

PROHIBITED_SCOPE:
- No real download or failed-job retry, no GANA-3223 state repair, no original MP4/TS/HLS/filelist/task cleanup or overwrite.
- No Writer, Gluetun, Selkies, Stage11 S11-WX011, NAS/Jellyfin change or restart; no protected dirty-worktree/candidate modification; no canonical product-code publication.
- Do not bypass Docker access restrictions, missing backup evidence, active-work risks, lock/reservation/no-clobber/retry guards or any unknown required gate. Stop and report BLOCKED if required evidence cannot be established.
- This record authorizes Downloader operations only; Discovery Writer Safety participates for shared-task traceability and preservation, not Writer implementation or operation. Existing Writer safety issue remains UNRESOLVED.
- No legacy MP4 recovery reexecution or old receipt reuse. Handoff NEXT text is never new authorization.

ACCEPTANCE: Report actual build/image/runtime/smoke/deployment/health/data/other-service/rollback evidence separately. A synthetic PASS is not operational download PASS. Complete the unified handoff even if deployment is BLOCKED.


## EXECUTION RESULT — GANA-3223 HLS overlay build/deployment BLOCKED (2026-10-22)

> TASK_ID: DLDWS-001; STATUS: IN_PROGRESS; CONTRACT_VERSION: 1.0.0; REQUIRES_WORKSTREAMS: downloader,discovery-writer-safety.

- Approval was identically registered and read back at 2908594f21b00589bb63f82a1ab557d5c0d2732b. Candidate teddy_mp4_queue.py SHA-256 matched 593b3ad77f50e2af64589d84a005fad5ce79495e4280011f3e240a6961ba9730.
- BUILD=NOT_RUN; DEPLOY=NOT_RUN; FINAL_IMAGE_SMOKE=NOT_RUN; NEW_IMAGE=NONE. A read-only Docker inspect failed with permission denied at unix:///var/run/docker.sock. No privilege escalation, alternate Docker endpoint, socket permission change or operational command was attempted.
- A separate safety blocker was found in read-only host work data: five ERROR tasks, max_concurrent=4; GANA task remains failed without local result, but its valid sealed queue job is output_ready and references a regular 2,353,735,715-byte output. Current Docker mount identity could not be reverified, so host-path evidence is not a fresh live-container identity proof.
- Actual unchanged _recover() and _eligible_job() were exercised in a temporary synthetic ERROR/output_ready fixture: startup changed status to MP4 waiting, saved task state once, and made one job eligible. No worker, remux or publication ran. Thus restarting the Downloader can itself violate the explicit no-GANA-state-change boundary. DEPLOYMENT_GATE=BLOCKED_GANA_STARTUP_REPLAY independently of Docker access. No source/hash/state bypass was introduced.
- Existing PVE data.tar is not visible at its host mount path in CT108; fresh trusted backup/source-manifest evidence is unavailable. Live Compose labels/config, current work/lock/retry idleness, dependency state and rollback compatibility remain INCOMPLETE. Historical deploy/rollback scripts pin obsolete 83322e/14f8c8 images and exactly four tasks; they were preserved and must not run unchanged.
- Prior offline smoke 13 groups PASS is reused; it used external import stubs and is not final-image or real-download verification. Current three small task/settings/GANA-job file hashes were equal before/after this investigation. Full fragment content hashes and production health were not retested.
- PRODUCTION_WRITES=NONE; CONTAINER_SERVICE_LIFECYCLE=NOT_RUN; ROLLBACK=NOT_RUN; CANONICAL_PRODUCT_CODE=NOT_PUBLISHED. Writer/Gluetun/Selkies/Stage11/NAS/Jellyfin and previous candidates/evidence were not changed. Writer safety issue remains UNRESOLVED. This Writer workstream record is shared-task coordination only.
- Evidence: /tmp/dldws001-hls-deploy-20261022.0P7fvZWM/execution-result.json, current-readonly-snapshot.json, state-readback.json, gana-startup-replay-synthetic.json and docker-access.txt.
- Unified next-chat handoff: /tmp/TEDDY_DOWNLOADER_UNIFIED_NEXT_CHAT_HANDOFF_20261022_AFTER_DEPLOY.md, finalized with the result commit readback SHA. Canonical CURRENT_HANDOFF includes the integrated state, blockers, legacy recovery and Stage11 scope.

NEXT: resolve the GANA startup-replay authorization/safety conflict and obtain fresh trusted Docker/backup/config/idle/rollback evidence before any operational action. Do not mutate GANA state, retry legacy recovery, reuse receipts, or treat historical NEXT text as approval.


## SEPARATE APPROVED EXECUTION — MP4 startup recovery safety implementation (2026-10-22)

> TASK_ID: DLDWS-001
> STATUS: IN_PROGRESS
> CONTRACT_VERSION: 1.0.0
> REQUIRES_WORKSTREAMS: downloader,discovery-writer-safety

USER_APPROVED_POLICY: Preserve explicitly failed MP4 jobs until the user explicitly retries; automatically resume only verifiably interrupted, normally incomplete work.

AUTHORIZED_SCOPE:
- Inspect the preserved actual runtime, startup/load/recovery/selection/execution/result/publication boundaries and existing evidence read-only.
- Prepare a NEW isolated candidate, preserving the prior HLS result fix candidate and its teddy_mp4_queue.py SHA-256 593b3ad77f50e2af64589d84a005fad5ce79495e4280011f3e240a6961ba9730.
- Implement the approved general policy without UUID/title-specific exceptions. Preserve explicit failures, ambiguous legacy records, source/output/queue hashes, normal consistent interruption resume, HLS/yt-dlp behavior and existing locks/reservations/no-clobber/retry safety.
- Use only synthetic temporary tasks and files for focused startup/repeated-startup, explicit-failure/ambiguity/paused/cancelled, execution/result/publication boundary, lock/reservation and HLS/yt-dlp regressions.
- Record candidate files, exact hashes, test outcomes and limitations. Only approval/result governance and handoff documentation may be published; product code remains isolated.

PROHIBITED_SCOPE:
- No Docker build/deploy/access workaround, container/service restart, operating task/queue/settings mutation, GANA or legacy-four-job recovery/retry, real download/production FFmpeg/NAS publication, source cleanup or receipt reuse.
- No Writer code/socket/systemd change; no Stage11, Gluetun, Selkies, Jellyfin/NAS change; no existing candidate or dirty-worktree overwrite/reset/clean; no canonical product-code commit/push; no weakening/skipping safety tests.
- Discovery Writer Safety records the shared-task authorization only; the implementation is Downloader MP4/startup scope and does not extend the Writer contract.
- Existing Docker access, backup/live-config and Writer safety blockers remain; isolated PASS never authorizes production deployment.

ACCEPTANCE:
- Explicit ERROR/failed jobs remain unchanged and unselected even with output_ready queue records.
- Consistent normal interruption resumes once, without converting real failures or ambiguous history into successful/retryable work.
- Failed-job policy is enforced at startup, selection, execution, result storage and publication boundaries; normal explicit retry remains possible only through its existing authorized path.
- Preserve original data, queue records, HLS result fix, yt-dlp compatibility and MP4 locking/reservation/collision guarantees; report all unverified conditions.

NEXT_CHECKPOINT: Review the isolated implementation and evidence; no build, deployment or operating recovery is authorized by this phase.


## EXECUTION RESULT — MP4 startup recovery safety candidate: INCOMPLETE / focused test FAIL (2026-10-22)

> TASK_ID: DLDWS-001; STATUS: IN_PROGRESS; CONTRACT_VERSION: 1.0.0; REQUIRES_WORKSTREAMS: downloader,discovery-writer-safety.

- The user-approved policy was registered identically in both ACTIVE_WORK files and read back at 869aa33e5c4ab3c0f24905d1211182e2db82bda2. Implementation/testing was isolated at /tmp/dldws001-mp4-startup-safety-20261022/. Existing HLS candidate and all previous evidence were preserved.
- IMPLEMENTATION=INCOMPLETE; SYNTHETIC_SMOKE=FAIL. One focused invocation ran 23 unittest methods in 0.721s, reporting failures=3 and errors=23 (includes subtests), exit 1. Per the explicit stop-on-failure instruction, no runtime/test edits or test reruns followed this failure.
- Twenty-three reported errors originate in the synthetic HLS fixture constructor: it writes remux-stage.mp4 before prepare_hls_resume creates the source-plan binding. The unchanged HLS safety guard correctly rejects that non-empty, unbound directory before the intended assertions run.
- The normal yt-dlp queued/running and late-postprocessor-failure assertions also failed. The test invocation mocked _make_ytdlp but did not isolate actual _rehydrate_additional_pps import; yt_dlp is absent in this Python 3.13.5 environment. No rerun/instrumented execution was performed to claim a final product-level outcome.
- Some yt-dlp failure-preservation, unchanged raw MP4 load, incomplete-descriptor hold, final-publication rejection, pre-publication failure and unmarked-queue preservation checks passed. These partial results do not establish GANA/HLS failure preservation, normal-interruption resume, ambiguity handling or overall regression PASS.
- Runtime candidate changes are app.py (MP4-owned load/auto-retry handling and checked persistence option), teddy_mp4_queue.py (non-mutating startup, failure/ambiguity admission at selection/execution/result boundaries and checked explicit retry), and teddy_download_safety.py (shared MP4 hold classification/final publication guard). All remain isolated and unvalidated for deployment.
- Candidate runtime SHA-256: app.py bbf306ef39cd57c63a09a672624cc243ef58fa99716f15bd78d3c6dbd2dccba3; teddy_mp4_queue.py cb583308c4b3a73b4580fb29dd4d0c63899e3d07fa33561bfc9843fb1ddc7649; teddy_download_safety.py 56c9a868736443fd05ec51b776dd948727d54495296dc254c8dc54fd1fad1ee9.
- Evidence: candidate README.md, evidence/startup-recovery-smoke.log and evidence/failure-result.json. The latter records exact hashes of three runtime and three changed/added test-support files, changed functions, partial results and unexecuted coverage. Before snapshots are under before/.
- Full 13-group HLS/yt-dlp regression, existing 12-case offline auth/queue suite, 11-case persistence regression and remaining required lock/reservation/mutation checks were NOT_RUN on this candidate after the failure. Prior candidates' PASS evidence is not transferred.
- Runtime source provenance: queue/safety/entrypoint/bootstrap from the preserved actual read-only live snapshot and HLS candidate; app.py matches the operator-verified 14f8c8 overlay at SHA a906e1013ebb7a0ee70b08b77ec32b7dd4fc99dbf5f4450904418abf2163bca2. Fresh live Docker/runtime identity was not reverified. Raw canonical app.py is not the final patched runtime and canonical root teddy_mp4_queue.py is absent; never overwrite deployed runtime wholesale from old local/canonical raw code.
- PRODUCTION_CHANGED=NO; BUILD=NOT_RUN; DEPLOY=NOT_RUN; DEPLOYMENT_GATE=BLOCKED; CANONICAL_PRODUCT_CODE=NOT_PUBLISHED. No operating state/source/file/service/Docker operation was performed. Owned synthetic temporary directories were cleaned by their test lifetime; no existing data was deleted.
- This Writer-workstream entry is coordination only. Existing Docker access, backup/source-manifest/live-configuration and Writer safety blockers remain unchanged and UNRESOLVED where previously recorded.

NEXT_CHECKPOINT: correct only the HLS fixture initialization order and test-only yt-dlp import isolation, retaining this failure log and every safety assertion; rerun the same focused suite, then execute the unrun regressions only if it passes. This correction/retest was not performed in this stopped checkpoint. No operational retry or deployment follows from partial results.


## SEPARATE APPROVED CHECKPOINT — focused startup test fixture/import correction (2026-10-22)

> TASK_ID: DLDWS-001; STATUS: IN_PROGRESS; CONTRACT_VERSION: 1.0.0; REQUIRES_WORKSTREAMS: downloader,discovery-writer-safety.
AUTHORIZATION: Explicit user instruction for focused test recovery; canonical baseline ba1a53a64dc79e867fe13653ef6fee3526b91984.

AUTHORIZED_SCOPE: Correct only the HLS synthetic fixture creation order and test-only external yt-dlp import isolation in /tmp/dldws001-mp4-startup-safety-20261022/. Preserve all existing assertions and add/preserve the negative unbound-precreated-output check. Execute the same tests/startup_recovery_smoke.py suite exactly once after correction; stop immediately on any failure/error. Record test hashes and actual results.
FROZEN_RUNTIME: app.py bbf306ef39cd57c63a09a672624cc243ef58fa99716f15bd78d3c6dbd2dccba3; teddy_mp4_queue.py cb583308c4b3a73b4580fb29dd4d0c63899e3d07fa33561bfc9843fb1ddc7649; teddy_download_safety.py 56c9a868736443fd05ec51b776dd948727d54495296dc254c8dc54fd1fad1ee9.
PROHIBITED: No runtime edits, full regression, Docker/build/deploy/restart, package installation/network test, operating task/queue/settings/media change, GANA/legacy recovery, Writer/Stage11/dependency change, canonical product-code commit/push, prior evidence overwrite or weakened safety assertion. Writer workstream participation is shared-task traceability only.
ACCEPTANCE: One focused result, unchanged runtime hashes and original failure evidence, preserved safety assertions; full regression remains NOT_RUN and deployment gate remains BLOCKED regardless of focused PASS.
NEXT_CHECKPOINT: Full regression requires the next separately scoped checkpoint; no operational action is authorized here.


## EXECUTION RESULT — focused startup fixture/import retest PASS (2026-10-22)

> TASK_ID: DLDWS-001; STATUS: IN_PROGRESS; CONTRACT_VERSION: 1.0.0; REQUIRES_WORKSTREAMS: downloader,discovery-writer-safety.

- Narrow test-only authorization was identically registered and remotely read back at 6c98351db922e1ff25394b3a53cb49516e3ee423. The previous failed checkpoint and its evidence remain unchanged; this later result does not rewrite that failure.
- TEST_FIXTURE_CORRECTION=PASS: the HLS fixture now creates its actual source-plan binding before segments, records their actual SHA, revalidates the binding/hash, then creates synthetic remux output. A negative subtest confirms a precreated unbound output is still rejected and its directory/files remain unchanged.
- YTDLP_TEST_ISOLATION=PASS: only external yt_dlp/postprocessor/ffmpeg import modules are scoped into the two existing fake-YDL test contexts. Actual _rehydrate_additional_pps and internal recovery, selection, result and publication checks execute unchanged. Empty external modules expose no fake PP classes; no package installation or network call was used.
- FOCUSED_SMOKE=PASS: exactly one invocation of PYTHONDONTWRITEBYTECODE=1 python3 tests/startup_recovery_smoke.py; Python 3.13.5; 23 unittest methods, failures=0, errors=0, exit=0 (unittest 1.667s). No further suite was executed.
- Tested scope includes explicit HLS/yt-dlp failed-job preservation, verified normal interruption resuming once, repeated recovery without duplicate publication, ambiguous/paused/cancelled holds, late-failure guards at execution/result/publication, source/result mutation rejection, explicit retry ENOSPC preservation and detection of the unsafe baseline recovery mutation. Synthetic task/queue/source/result snapshots are checked by the preserved assertions; this is not production or real-media evidence.
- Only two test files changed: teddy_mp4_queue_smoke.py SHA-256 bca56172e1bd98bfd016cfef043967a4d143fd56691695d0a574fddd0e61a981; tests/startup_recovery_smoke.py SHA-256 77ffda038b0346cd760032aa2ba78ccfd5a345c236a14244e3b7ae9a946b6470.
- RUNTIME_SHA_UNCHANGED=YES: app.py bbf306ef39cd57c63a09a672624cc243ef58fa99716f15bd78d3c6dbd2dccba3; teddy_mp4_queue.py cb583308c4b3a73b4580fb29dd4d0c63899e3d07fa33561bfc9843fb1ddc7649; teddy_download_safety.py 56c9a868736443fd05ec51b776dd948727d54495296dc254c8dc54fd1fad1ee9.
- SAFETY_ASSERTIONS_PRESERVED=YES: AST comparison retains every original assertion and all 23 test method identities; new assertions add negative fixture coverage. Syntax/diff whitespace checks passed. Before snapshots, startup_fixture_support.py, prior failure log/JSON, prior README and original HLS candidate hashes remain unchanged. No owned synthetic test directories remain.
- Evidence: /tmp/dldws001-mp4-startup-safety-20261022/evidence/focused-fixture-retest-91ov7fji/ (result.json, focused-smoke.log, execution.json, attempt.json, pre-run-static.json, test-correction.diff, test-before/ and protected-before/after.json).
- FULL_REGRESSION=NOT_RUN; PRODUCTION_CHANGED=NO; BUILD=NOT_RUN; DEPLOY=NOT_RUN; DEPLOYMENT_GATE=BLOCKED. No canonical product/test code was published. Existing Docker access, fresh backup/live configuration and unresolved Writer socket safety blockers remain. Writer participation is coordination only; Stage11 and all operating services/data remain untouched.

NEXT_CHECKPOINT: the separately scoped full regression on this frozen runtime candidate: 13-group HLS/yt-dlp smoke, existing auth/queue and persistence regressions, and remaining lock/reservation/concurrency checks with their offline dependency setup. This focused PASS grants no operating recovery/retry/build/deployment permission.


## SEPARATE APPROVED CHECKPOINT — frozen MP4 startup safety full offline regression (2026-10-22)

> TASK_ID: DLDWS-001; STATUS: IN_PROGRESS; CONTRACT_VERSION: 1.0.0; REQUIRES_WORKSTREAMS: downloader,discovery-writer-safety.
AUTHORIZATION: Explicit user approval for verification only; canonical baseline f89985a0d7d05c8e663af68f939d9695691d9990.
TARGET: /tmp/dldws001-mp4-startup-safety-20261022/. Verify frozen hashes before/after: app.py bbf306ef39cd57c63a09a672624cc243ef58fa99716f15bd78d3c6dbd2dccba3; teddy_mp4_queue.py cb583308c4b3a73b4580fb29dd4d0c63899e3d07fa33561bfc9843fb1ddc7649; teddy_download_safety.py 56c9a868736443fd05ec51b776dd948727d54495296dc254c8dc54fd1fad1ee9; teddy_mp4_queue_smoke.py bca56172e1bd98bfd016cfef043967a4d143fd56691695d0a574fddd0e61a981; tests/startup_recovery_smoke.py 77ffda038b0346cd760032aa2ba78ccfd5a345c236a14244e3b7ae9a946b6470.
AUTHORIZED_SCOPE: Inspect the original commands and offline dependencies; execute each existing suite at most once in order: HLS/yt-dlp 13 groups, auth/queue 12 cases, persistence 11 cases, then existing applicable MP4 lock/reservation/concurrency safety checks. Use only synthetic isolated files and external dependency isolation; never replace product safety checks with mocks. Stop subsequent suites on any failure/error. Missing safe dependencies block execution without install/network workarounds. Record actual counts, gaps, hashes and fresh unique evidence; reuse the prior focused 23/23 PASS without claiming unexecuted coverage.
PROHIBITED: No frozen runtime/test edits, package installation, real download or operating media/task/queue/settings access as fixtures, GANA/legacy reprocessing, Docker access changes/build/deploy/restart, Writer/Stage11/Gluetun/Selkies/Jellyfin/NAS changes, old candidate/evidence overwrite, weakened assertions or canonical product/test publication.
ACCEPTANCE: Report actual per-suite outcomes and coverage gaps, unchanged runtime/tests and preserved history. Only approval/result documentation may be published. Writer participation is shared-task traceability only. Docker access, fresh backup/live configuration and Writer safety blockers remain; DEPLOYMENT_GATE=BLOCKED regardless of offline results.
NEXT_CHECKPOINT: Review the actual regression outcome; no production action follows from a technical PASS.


## EXECUTION RESULT — frozen MP4 startup full regression stopped on caught test-harness error (2026-10-22)

> TASK_ID: DLDWS-001; STATUS: IN_PROGRESS; CONTRACT_VERSION: 1.0.0; REQUIRES_WORKSTREAMS: downloader,discovery-writer-safety.

- Full offline verification approval was identically registered in both ACTIVE_WORK files and remotely read back at 519ec0d70e7b7315d9f37dfeebd0a4fc91aff846. Frozen runtime/test hashes and prior evidence matched before execution. No runtime or test code was edited.
- FULL_REGRESSION=FAIL; HLS_YTDLP_13_GROUPS=PASS; AUTH_QUEUE_12_CASES=FAIL (invalid automatic-retry coverage); PERSISTENCE_11_CASES=NOT_RUN; LOCK_RESERVATION_CONCURRENCY=INCOMPLETE; DEPLOYMENT_GATE=BLOCKED.
- Suite 1: exactly one existing invocation of PYTHONDONTWRITEBYTECODE=1 python3 run_smoke_with_external_stubs.py from the frozen candidate. All 13 groups passed, failed=0, errors=0, exit=0, Python 3.13.5. Existing external yt-dlp/transport stubs, synthetic files and an isolated Python remux-child stand-in were reused; no real download/operating FFmpeg/network was run.
- Suite 2: exactly one invocation of unchanged legacy tests/offline_tests.py using the existing /tmp/dl001-py310-testenv-20261019/bin/python (3.10.22; Flask 3.1.3; Werkzeug 3.1.9). Byte-identical test copies and the existing OVERLAY_TEST_ROOT/RUNTIME/BASE_MODULES switches routed output to new evidence and main code to the frozen runtime. Formal unittest result: 12 run, 12 passed, 0 failures, 0 errors, exit=0.
- Despite that formal result, the log contains one real caught execution error: "[자동재시도] 오류: name 'teddy_mp4_queue' is not defined". The original AST test namespace in test_actual_auto_manual_bulk_race omits teddy_mp4_queue and DOWNLOAD_DIR required by frozen app.py:auto_retry_monitor (line 874). The actual monitor catches/logs NameError; another producer still queues the job and the old assertions pass without exercising automatic retry admission. Therefore acceptance FAIL is required; the formal green result is not valid evidence for the intended concurrency property. This is a test-harness compatibility error, not evidence that the complete operating app lacks its imports.
- Stop-on-error was applied after this observation: no persistence suite, supplemental suite, automatic fix or rerun followed. Persistence: 0 run, 0 passed, 0 failures, 0 errors / NOT_RUN. No previous candidate PASS was substituted.
- Current-run positive coverage includes HLS/yt-dlp result and source-plan/SHA/path checks, no-clobber collision protection, pause/cancel behavior, current queue cross-process serialization, global MP4 exclusion and live storage reservation during the synthetic remux child; real Flask auth/CSRF/capacity/inode/fragment assertions also executed.
- SAFETY_COVERAGE_GAPS: automatic/manual/bulk race is unverified due to the caught NameError; 11-case persistence and remaining reservation/ENOSPC/ownership/admission coverage were not run. The legacy auth test's child-lock and baseline hash assertions use the old BASE_CONTEXT, so they cannot be represented as current-runtime proof (suite 1 separately exercises the current queue lock). Its individual MP4 retry test mocks the dispatch target, proving routing only. Prior focused 23/23 failure/ambiguity/late-publication evidence is reused and was not rerun.
- RUNTIME_SHA_UNCHANGED=YES; TEST_SHA_UNCHANGED=YES. Entire recorded candidate/prior HLS candidate/test-input byte inventories match before/after. Existing failure and success logs, before/ snapshots and protected worktrees remain untouched; no owned synthetic test directories remain.
- New evidence: /tmp/dldws001-mp4-startup-safety-20261022/evidence/full-regression-jt5u5cxi/. Contains plans/attempts, hls-ytdlp-13.log, auth-queue-12.log, unchanged legacy test copies, coverage.json, STOP.json, before/after-sha256.json and result.json. result.json SHA-256 af5f571f9992a6c7b19e5863b376df0205cf93617fb0c608b9166d0cff26eff6.
- PRODUCTION_CHANGED=NO; BUILD=NOT_RUN; DEPLOY=NOT_RUN; CANONICAL_PRODUCT_CODE=NOT_PUBLISHED. Only governance/handoff documentation was published. Docker access, current trusted backup, live configuration verification and the unresolved Writer socket safety problem remain independent blockers. Writer participation is shared-task tracking only; operating GANA/legacy tasks, media, dependencies and Stage11 were not touched.

NEXT_CHECKPOINT: separately authorize the minimal test-only AST namespace compatibility correction (also review the same boundary in the unrun persistence suite) and assertions that detect an automatic-producer error/bypass. Preserve frozen product code and this failure evidence; do not repeat or extend operational work.


## SEPARATE APPROVED CHECKPOINT — auth/queue AST test environment repair (2026-10-23)

> TASK_ID: DLDWS-001; STATUS: IN_PROGRESS; CONTRACT_VERSION: 1.0.0; REQUIRES_WORKSTREAMS: downloader,discovery-writer-safety.
AUTHORIZATION: User explicitly approved test-only AST namespace repair and hidden-exception detection, followed by one existing 12-case auth/queue suite invocation; baseline 3bb1544eb6ed528dca4ec7a20a4eed3c818f3da1.
AUTHORIZED_SCOPE: Work only on a NEW evidence-area copy of the legacy auth/queue test. Bind actual frozen candidate teddy_mp4_queue and owned synthetic DOWNLOAD_DIR; inspect other globals; retain real automatic-retry/selection/admission logic. Add independent execution/admission/state evidence and detection of internally caught errors, preserving existing race/duplicate and safety assertions. Negative detector checks may run inside the same test. Read the persistence suite namespace only; do not modify or execute it. Reuse Python 3.10.22 offline environment; execute only the 12-case suite once, stop on failure without fixes/reruns.
FROZEN: Preserve app.py bbf306ef39cd57c63a09a672624cc243ef58fa99716f15bd78d3c6dbd2dccba3; teddy_mp4_queue.py cb583308c4b3a73b4580fb29dd4d0c63899e3d07fa33561bfc9843fb1ddc7649; teddy_download_safety.py 56c9a868736443fd05ec51b776dd948727d54495296dc254c8dc54fd1fad1ee9; teddy_mp4_queue_smoke.py bca56172e1bd98bfd016cfef043967a4d143fd56691695d0a574fddd0e61a981; tests/startup_recovery_smoke.py 77ffda038b0346cd760032aa2ba78ccfd5a345c236a14244e3b7ae9a946b6470.
PROHIBITED: No product/frozen-test/persistence-test edit, prior evidence overwrite, canonical product/test publication, full regression rerun, operating data/service access as fixtures, real download/media/retry, Docker/install/network workaround or Writer/Stage11/dependency change. Writer participation is shared-task documentation only.
ACCEPTANCE: 12 cases pass with zero unexpected caught errors and independent real automatic-producer evidence; frozen SHA and original evidence unchanged. Even PASS leaves FULL_REGRESSION=INCOMPLETE, PERSISTENCE_11_CASES=NOT_RUN, BUILD/DEPLOY=NOT_RUN and DEPLOYMENT_GATE=BLOCKED. Record only actual outcome in both active documents and handoff, with readback.


## EXECUTION RESULT — auth/queue AST test repair and one 12-case retest PASS (2026-10-23)

> TASK_ID: DLDWS-001; STATUS: IN_PROGRESS; CONTRACT_VERSION: 1.0.0; REQUIRES_WORKSTREAMS: downloader,discovery-writer-safety.

- The separate test-only approval was identically registered and remotely read back at b03a63187504bb119b7ed6e4974592fce96d3a6c. Previous failure evidence under evidence/full-regression-jt5u5cxi/ remains byte-identical; the old caught NameError has no stored traceback because the real monitor caught/logged it.
- AST_NAMESPACE_FIX=PASS: only the new evidence-area tests/offline_tests.py copy was changed. The real auto_retry_monitor is AST-extracted unchanged and receives the actual frozen candidate teddy_mp4_queue plus the fixture-owned temporary DOWNLOAD_DIR. Static symbol-table review found no remaining non-builtin global dependency missing from this namespace. Frozen mp4/safety/admin module paths and hashes were checked in the existing Python 3.10 environment before execution; app startup was never imported.
- HIDDEN_EXCEPTION_DETECTION=PASS; AUTO_RETRY_PRODUCER_EXECUTED=YES: observers verify actual monitor code as the caller of its two iteration-boundary checks and its checked persistence callback. The persistence observer delegates unchanged to the real transaction, then records selected task, previous state, memory, persisted bytes and queue. auto-first records exactly one automatic admission, retries 0->1, pending state and identical memory/disk record. bulk-first records one real monitor iteration with no duplicate admission and unchanged pending state/retries 0. Both threads' exceptions are collected. Original lock/blocking/manual duplicate assertions remain.
- Hidden caught exceptions are collected from active sys.exc_info at the test-local print boundary, not inferred solely from success log strings. Within the same test, deliberate missing-module NameError and wrong-module AttributeError are each rejected by the same acceptance assertions; disabled-monitor admission bypass is also rejected independently of error logs. All three negative cases preserve synthetic tasks, state-file bytes, empty queue and fragment SHA. The two injected caught errors are expected negative evidence, not unexpected errors.
- AUTH_QUEUE_12_CASES=PASS: exactly one invocation of /tmp/dl001-py310-testenv-20261019/bin/python tests/offline_tests.py with the existing OVERLAY_TEST_ROOT/RUNTIME/BASE_MODULES settings targeting the new evidence root and frozen runtime. Python 3.10.22; Flask 3.1.3; Werkzeug 3.1.9. Tests run=12, passed=12, failures=0, errors=0, exit=0; UNEXPECTED_CAUGHT_ERRORS=0; detector negative checks=3. No retries or other suite execution followed.
- Only test_actual_auto_manual_bulk_race and test result/audit reporting changed; all other 11 test method ASTs are identical, every old assertion is retained, the suite still has 12 test methods, Python 3.10 syntax and diff whitespace checks passed. Changed test SHA-256: fb3190a72691410fb44fd76a4fa18c7fb472fa093a5366415f23d85e85e81492.
- RUNTIME_SHA_UNCHANGED=YES; FROZEN_TEST_SHA_UNCHANGED=YES; OLD_EVIDENCE_UNCHANGED=YES. The three frozen runtime hashes and both focused/queue smoke hashes still match the approved values. Recorded preexisting candidate/evidence/persistence-source inventories are equal before/after. No owned synthetic test directories remain.
- PERSISTENCE_PRECHECK=ISSUES_FOUND: read-only AST review of the unrun test_auto_retry_uses_checked_transaction finds the same missing teddy_mp4_queue and DOWNLOAD_DIR globals. Its unchanged-state assertions also do not prove the injected persistence failure boundary was reached. The file SHA remains 7af6d001bf589efae30de096eb7f8fafd5774622f2c02fe9fa119c8e16ff4822. It was neither modified nor executed.
- New evidence: /tmp/dldws001-mp4-startup-safety-20261022/evidence/auth-queue-repair-yugxzyfw/ (tests/offline_tests.py, offline_tests.before.py, test-changes.diff, static-review.json, attempt.json, execution.json, auth-queue-12.log, evidence/auto-retry-audit.json, evidence/host-offline-results.json, protected-before/after.json, result.json). result.json SHA-256 107d9caeeb3c6db1f809ac4d29012341501b4ac05d44f8cfc020058fe3534968.
- PERSISTENCE_11_CASES=NOT_RUN; FULL_REGRESSION=INCOMPLETE; PRODUCTION_CHANGED=NO; BUILD=NOT_RUN; DEPLOY=NOT_RUN; DEPLOYMENT_GATE=BLOCKED. The previously passed HLS/yt-dlp 13 groups and focused 23 tests were not repeated. Remaining reservation/ENOSPC/ownership/concurrency checks were not executed. The legacy baseline-context child-lock/hash check and mocked individual MP4 retry dispatch still have their previously documented coverage limits.
- Only approval/result governance and handoff documents were published; no canonical product/test source was committed. No operating data/service/queue/media or Docker action, real download, Writer/Stage11/dependency change or package installation occurred. Docker access, fresh backup/live configuration and unresolved Writer socket safety remain blockers. Writer workstream participation is history tracking only.

NEXT_CHECKPOINT: separately scoped test-only repair of the persistence suite's missing globals and proof that injected storage faults are actually reached, then one 11-case execution. This 12-case PASS does not complete full regression or authorize deployment.


## DOCUMENT-FORMAT MAINTENANCE — DLDWS-001 (2026-10-23)

- User-approved records-only repair for repeated historical workstream fields; canonical HEAD at preflight `ac476f4a822317576d9963a638e78ee8abe14344`.
- Original document preserved byte-for-byte at `docs/governance/discovery-writer-safety/history/DLDWS-001_ACTIVE_WORK_before_field_normalization_ac476f4.md`, verified against original blob `348c0957a5feb0833dfd1467a07cf9f995e373b8`.
- Unchanged five-line current-state metadata: `discovery-writer-safety / IN_PROGRESS / DLDWS-001 / contract 1.0.0 / downloader,discovery-writer-safety`.
- Historical field lines quoted only; every original approval/result value and chronology remain present. Governance checker, router, contracts, Stage11 and operating product files untouched.
- Do not repeat raw column-zero metadata labels in later historical checkpoints; this is not new operational approval. Docker, backup, live configuration and Writer safety gates remain BLOCKED.


## SEPARATE USER-APPROVED CHECKPOINT — offline persistence 11-case harness repair (2026-10-23)

> TASK_ID: DLDWS-001; STATUS: IN_PROGRESS; CONTRACT_VERSION: 1.0.0; REQUIRES_WORKSTREAMS: downloader,discovery-writer-safety.

- AUTHORIZATION: User explicitly approved continuing the next Downloader task after the GitHub workstream-record validation repair. That cross-workstream document normalization was verified on canonical commit `b94be7e042a09772fb21bf86858d381d71b673da`; its unchanged Project Governance CI PASS must remain preserved.
- OBJECTIVE: In the isolated MP4 Startup Safety candidate `/tmp/dldws001-mp4-startup-safety-20261022/`, repair only the copied persistence 11-case test harness's AST namespace dependencies (`teddy_mp4_queue`, fixture-owned `DOWNLOAD_DIR`, and other actual verified globals), and add fail-closed assertions proving the real injected persistence fault boundary is actually reached and errors cannot be swallowed as a false PASS. Execute the same 11-case offline suite once after correction, only if source/contract/preconditions match.
- PRIOR EVIDENCE: `/tmp/dldws001-mp4-startup-safety-20261022/evidence/auth-queue-repair-yugxzyfw/result.json`; auth/queue 12-case corrected test PASS; read-only persistence precheck ISSUES_FOUND. Prior persistence source SHA-256 recorded `7af6d001bf589efae30de096eb7f8fafd5774622f2c02fe9fa119c8e16ff4822`; verify exact original file and byte identity before changes.
- FROZEN PRODUCT SHA-256: `app.py=bbf306ef39cd57c63a09a672624cc243ef58fa99716f15bd78d3c6dbd2dccba3`; `teddy_mp4_queue.py=cb583308c4b3a73b4580fb29dd4d0c63899e3d07fa33561bfc9843fb1ddc7649`; `teddy_download_safety.py=56c9a868736443fd05ec51b776dd948727d54495296dc254c8dc54fd1fad1ee9`.
- ALLOWED: Create a new isolated evidence directory and test-only copy; preserve every previous assertion/test identity; add independently observable injected-fault reached and caught-exception detection; verify safe offline Python 3.10 setup; run 11 tests once. Stop on first suite failure/error and report. Review only relevant source without editing product runtime. Document hashes, results, gaps and unchanged original evidence; readback the shared-task result documentation if produced.
- PROHIBITED: No product runtime/frozen test mutation, old evidence overwrite, changes to governance validation rules, real downloading/retry/remux, operational GANA/legacy job/task/queue/settings/media/NAS change, Docker build/deploy/restart/socket permission workaround, Writer socket/code, Stage11, Gluetun, Selkies, Jellyfin modification, hidden-error tolerance, weakened assertions, package/network workaround, canonical product/test publication or unapproved suites.
- ACCEPTANCE: Actual test method count and exit; zero unexpected swallowed errors; fault injection verifiably reached; input/result/state preserved as asserted; before/after SHA readback; `PRODUCTION_CHANGED=NO`, `BUILD=NOT_RUN`, `DEPLOY=NOT_RUN`, `DEPLOYMENT_GATE=BLOCKED` regardless of technical result. Writer participation is shared-task coordination only. HLS/yt-dlp 13-group and auth/queue 12-case earlier PASS are not rerun or inflated into full-regression PASS.
- NEXT_DECISION: Evaluate persistence result, then separately authorize remaining lock/reservation/ENOSPC/ownership/concurrency verification. This approval authorizes no live operation.


## EXECUTION RESULT — isolated persistence harness repair and 11-case test PASS (2026-10-23)

> TASK_ID: DLDWS-001; STATUS: IN_PROGRESS; CONTRACT_VERSION: 1.0.0; REQUIRES_WORKSTREAMS: downloader,discovery-writer-safety.

- The already registered checkpoint at approval commit 294604cd0dfa0fff5d3227a45e6ff69513cba5f2 was verified identically in both workstream records; no duplicate approval registration or live-state metadata was added. Approval Project Governance run 39871943314 completed successfully. Historical metadata normalization, original archives, CI policy, router and contracts remain unchanged.
- PERSISTENCE_AST_FIX=PASS: the new evidence-area copy of state_persistence_regression.py binds actual frozen teddy_mp4_queue and the fixture-owned DOWNLOAD_DIR in the actual auto_retry_monitor AST namespace. Symbol-table review finds no missing primary non-builtin globals. The existing corrected auth/queue fixture module is copied byte-identically for imports only; its 12-case suite is not run.
- FAULT_INJECTION_REACHED=YES; HIDDEN_EXCEPTION_DETECTION=PASS. Test observers delegate to the real checked persistence function without changing its save/rollback/queue decisions. Each injected exception object must appear in the actual propagated cause/context chain; ordinary unexplained exceptions are rejected rather than accepted merely because an expected fault also occurred. Known preexisting file collisions require matching FileExistsError paths. Observers inspect active exceptions at test-local logging, not success strings alone.
- Positive evidence includes 11 injected fault observations (open/partial-write/flush/file-fsync/replace/directory-fsync/queue-append, including two persistent-fsync errors) and two real no-clobber collision boundaries. The actual automatic producer calls checked persistence once, reaches its open ENOSPC, logs that same propagated transaction error, and retains original memory/state-file/queue/fragment invariants.
- Within the same automatic-retry test, deliberately missing-module NameError and disabled-monitor bypass both cause the same acceptance guard to reject absent transaction/fault execution. Both preserve synthetic task/state/queue/fragment bytes. The one deliberate NameError is expected negative evidence; UNEXPECTED_CAUGHT_ERRORS=0.
- PERSISTENCE_11_CASES=PASS: exactly one invocation of /tmp/dl001-py310-testenv-20261019/bin/python tests/state_persistence_regression.py, using existing OVERLAY_TEST_ROOT/RUNTIME/BASE_MODULES settings pointing to new evidence and frozen runtime. Python 3.10.22, Flask 3.1.3, Werkzeug 3.1.9. Tests run=11, passed=11, failures=0, errors=0, exit=0; unittest elapsed 1.772s. No follow-up suite or rerun was executed.
- Original source SHA-256 7af6d001bf589efae30de096eb7f8fafd5774622f2c02fe9fa119c8e16ff4822 was verified at /tmp/dldws001-mp4-startup-safety-20261022/evidence/full-regression-jt5u5cxi/legacy-harness/tests/state_persistence_regression.py. All old assertions and all 11 test IDs remain; syntax/diff checks passed. Only the new test copy changes: SHA-256 b35cfb9e77471709fafb7567d41b3931df4bbec6db20f67dcda9580daaac5377. Its copied offline_tests.py fixture stays fb3190a72691410fb44fd76a4fa18c7fb472fa093a5366415f23d85e85e81492.
- RUNTIME_SHA_UNCHANGED=YES; ORIGINAL_TEST_EVIDENCE_PRESERVED=YES. Frozen app.py bbf306ef39cd57c63a09a672624cc243ef58fa99716f15bd78d3c6dbd2dccba3, teddy_mp4_queue.py cb583308c4b3a73b4580fb29dd4d0c63899e3d07fa33561bfc9843fb1ddc7649 and teddy_download_safety.py 56c9a868736443fd05ec51b776dd948727d54495296dc254c8dc54fd1fad1ee9 remain identical. Recorded prior candidate, focused tests, original persistence source and historical evidence inventories match before/after; no owned synthetic test directories remain.
- Evidence: /tmp/dldws001-mp4-startup-safety-20261022/evidence/persistence-repair-3_smdk0f/ (tests/state_persistence_regression.py, unchanged fixture import, state_persistence_regression.before.py, static-review.json, changes.diff, attempt.json, execution.json, persistence-11.log, evidence/fault-audit.json, evidence/state-persistence-regression.json, protected-before/after.json, result.json). result.json SHA-256 db0926d46237764084f5905f23d3b9e369298835a710831e251ce844c4bc1677.
- FULL_REGRESSION=INCOMPLETE; PRODUCTION_CHANGED=NO; BUILD=NOT_RUN; DEPLOY=NOT_RUN; DEPLOYMENT_GATE=BLOCKED. Prior HLS/yt-dlp 13-group, focused 23-case and auth/queue 12-case results were reused, not repeated. Remaining lock/reservation/ENOSPC/ownership/concurrency verification was not performed. Persistent directory-fsync failure still leaves crash durability UNKNOWN, although tested admission is refused and prior in-process bytes/memory are restored.
- Product/runtime/test code was not published to canonical. Only result documentation is appended with historical task metadata quoted. No operating Docker/task/queue/settings/media/NAS or service action, real download/FFmpeg/publication, Writer/Stage11/Gluetun/Selkies/Jellyfin change or dependency installation occurred. Writer participation is coordination only. Docker access, fresh trusted backup, live configuration and unresolved Writer socket safety remain independent blockers.

NEXT_CHECKPOINT: remaining isolated lock/reservation/ENOSPC/ownership/concurrency regression verification; requires its separately scoped execution checkpoint. This technical 11-case PASS neither completes full regression nor authorizes deployment.


## SEPARATE USER-APPROVED CHECKPOINT — isolated MP4 lock/reservation/ENOSPC/ownership/concurrency regression (2026-10-23)

> TASK_ID: DLDWS-001; STATUS: IN_PROGRESS; CONTRACT_VERSION: 1.0.0; REQUIRES_WORKSTREAMS: downloader,discovery-writer-safety.

- AUTHORIZATION: Explicit user approval in the current chat, after the isolated persistence 11-case PASS recorded at canonical `ae0165d43a42a42ab43933af70dafab6b1b7c0bf`. This permits the remaining scoped offline safety regression only, **not** product edits, operational recovery or deployment.
- OBJECTIVE: Validate the already-frozen MP4 startup safety runtime under isolated/synthetic lock exclusivity (including cross-process contenders), reservation accounting / ENOSPC at admission and runtime, ownership and no-clobber collisions, and automatic/manual/bulk concurrency and duplicate-admission prevention. Preserve explicit ERROR/failed queue hold, safe normal-interruption resume, PAUSED/CANCELLED/ambiguous holds, and publication constraints. Distinguish actual executed paths from mocked routing or old baseline-context checks. Report any uncovered branch as COVERAGE_GAP, not PASS.
- TARGET: Existing isolated candidate `/tmp/dldws001-mp4-startup-safety-20261022/`; frozen app.py SHA-256 `bbf306ef39cd57c63a09a672624cc243ef58fa99716f15bd78d3c6dbd2dccba3`; teddy_mp4_queue.py `cb583308c4b3a73b4580fb29dd4d0c63899e3d07fa33561bfc9843fb1ddc7649`; teddy_download_safety.py `56c9a868736443fd05ec51b776dd948727d54495296dc254c8dc54fd1fad1ee9`. Verify test files and existing evidence inventories/readbacks against their recorded hashes.
- REUSED EVIDENCE: HLS/yt-dlp 13-group PASS, startup focused 23-method PASS, auth/queue 12-case PASS, persistence 11-case PASS; no reruns or implied broader proof. Separate last persistence result under `evidence/persistence-repair-3_smdk0f/`. Persistent directory-fsync crash-durability remains UNKNOWN without a dedicated authorized crash test.
- ALLOWED: Read-only preflight to map applicable previously approved offline tests and actual current-runtime execution pathways. Run safe existing targeted offline tests using existing dependency isolation, plus the smallest test-only fixtures/assertions needed to close concrete uncovered properties, in fresh isolated evidence directories. Use temp-owned files, synthetic queues, bounded child processes, strict cleanup of owned temp assets and before/after source/data hashes. Verify no unexpected caught errors; stop after first failure or unsafe/unknown precondition. Do not change any product runtime or protected candidates. Report actual test counts and every unknown.
- SAFETY MATRIX: (1) globally one MP4 executor despite multiple contenders and processes, lock release only by owner; (2) reservation prevents oversubscription and releases correctly on abort/ENOSPC, preserved partials; (3) file/path ownership, no-clobber/collision and publication race protections; (4) simultaneous auto/manual/bulk producers never bypass failure hold, duplicate admission or transactional persistence; (5) pause/cancel/ambiguous/error protections throughout selection, execution and publication. Test with isolated injectors/stubs only where external side effects would otherwise occur, never stub internal safety checks. Verify state/queue/media byte invariants.
- PROHIBITED: No Docker/Compose/socket privilege work, build/deploy/restart or operating-service action; no real download/remux/FFmpeg/NAS publication, GANA or four legacy jobs/production tasks/queue/settings/media or protected dirty-worktree mutation; no Writer socket/code/test operation, Stage11, Gluetun, Selkies or Jellyfin changes; no canonical product/test source publication, frozen runtime edits, package install/network workaround, disabling safety guards, broad host scans, or alteration/deletion of old evidence.
- ACCEPTANCE: Separate LOCK, RESERVATION_ENOSPC, OWNERSHIP_NO_CLOBBER, CONCURRENCY, FAILED_JOB_HOLD and COVERAGE_GAPS outcomes, with positive+negative evidence tied to actual runtime (not formal green-only). Record suite/test counts, tool/runtime hashes before/after, any tests added, test-only changes, exact evidence path and bytes-invariant observations; abstain from FULL_REGRESSION=PASS if any requested case remains untested. Product code and operations unchanged. BUILD=NOT_RUN, DEPLOY=NOT_RUN, DEPLOYMENT_GATE=BLOCKED regardless of technical result. Writer workstream entry is cross-workstream traceability only; unresolved Docker, backup/source-manifest/live-config, Writer safety and durability gates persist.
- NEXT_DECISION: Review isolated regression findings and coverage gaps; do not infer production readiness or authorize deployment from this checkpoint.


## EXECUTION RESULT — residual MP4 safety regression stopped on inherited-lock ownership FAIL (2026-10-23)

> TASK_ID: DLDWS-001; STATUS: IN_PROGRESS; CONTRACT_VERSION: 1.0.0; REQUIRES_WORKSTREAMS: downloader,discovery-writer-safety.

- The already registered shared checkpoint at 877205ce60d02092c6ba99ae5e41e2bc0613f76b matched both workstreams and its Project Governance run 39873219653 completed successfully. No duplicate approval or live-state metadata was added. Frozen runtime/test provenance and the four previous scoped PASS records were verified before execution; their suites were not rerun.
- First map the gaps: previous current queue-flock, remux-child, failure-hold, auth/queue and persistence evidence did not establish release authority on fork-inherited MP4 lock objects, complete reservation accounting/ENOSPC, concurrent output ownership or real individual-MP4 retry dispatch concurrency. An explicit coverage-plan.json preserves the reused versus pending boundaries.
- Executed once, fail-fast, Python 3.10.22: four targeted lock checks; 3 PASS / 1 FAIL / 0 ERROR. Existing unmodified _test_download_width_with_serial_remux passed (2/4 threaded contenders, actual RemuxTransaction maximum=1). Existing _test_process_lock_and_task_claim passed (cross-process storage/MP4 exclusivity and duplicate task claims). Existing _test_cancel_and_lock_failure passed (cancellation while waiting and permission failure). These were selected from the existing safety smoke, not a rerun of any previously passed complete suite.
- New test_04_non_acquirer_release_cannot_open_parent_critical_section FAIL: parent PID 4 acquired the actual MP4 lock; a separate unsuccessful lock object's release left it protected. A fork child PID 15 then used the inherited actual lock object/FD without calling acquire, and release returned normally. The parent still had acquired=True and its FD open and had not ended its critical section, yet an independent new contender acquired the same lock. Actual observation and AssertionError traceback are preserved.
- Scope of this finding: the shared open-file-description / inherited lock-object boundary. It does not establish an operating incident or that an unrelated process can release an inaccessible descriptor. InterProcessFileLock.release currently performs flock(LOCK_UN) using self.acquired/self.fd without checking the acquiring process identity. The expected non-acquirer-release safety property is therefore FAIL in this concrete scenario. No product implementation was changed or proposed as already fixed.
- Per stop-on-failure policy, no remaining reservation, runtime ENOSPC, concurrent-output ownership/no-clobber or actual MP4 auto/manual/bulk extension ran. No test/runtime fix or retry followed. Normal failure/paused/cancelled/ambiguous holds and validated normal interruption are reused only from the prior focused 23-case evidence.
- LOCK_EXCLUSIVITY=FAIL; RESERVATION_ENOSPC=INCOMPLETE; OWNERSHIP_NO_CLOBBER=INCOMPLETE; AUTO_MANUAL_BULK_CONCURRENCY=INCOMPLETE; FAILED_JOB_HOLD=PASS (reused prior scoped evidence); FULL_REGRESSION=FAIL. TESTS_RUN=4, PASSES=3, FAILURES=1, ERRORS=0; UNEXPECTED_CAUGHT_ERRORS=0.
- SAFETY_COVERAGE_GAPS: non-acquirer release ownership failed; remaining reservation/ENOSPC, ownership/queue-identity/collision and real individual-MP4 retry concurrency were not run after failure. Persistent directory-fsync crash durability remains UNKNOWN. Earlier mocked individual retry dispatch and old BASE_CONTEXT lock/hash checks are not substituted for current-runtime proof.
- Evidence: /tmp/dldws001-mp4-startup-safety-20261022/evidence/remaining-safety-sq81cb50/. Includes coverage-plan.json, static-review.json, attempt.json, execution.json, lock-boundary.log, evidence/lock-suite-result.json, evidence/lock-owner-observation.json, STOP.json, protected-before/after.json and result.json. result.json SHA-256 ac2ab8d1687579cb427739b7040352008cfdd29ca4665106edcfda94b06161e5.
- New test file tests/lock_boundary_checks.py SHA-256 58e2259ec6da541778546b014b9055fcbaa2a4d14f5212ca14fbaa10b219a6ce. Copied existing safety smoke tests/existing_download_safety_smoke.py SHA-256 6b3140673fb579e023fbb3069909bff99357521226a7e84512050f7dd966e5e8 is byte-identical to its original; existing assertions remain intact. Locks and RemuxTransaction were real; no lock or internal safety decision was mocked.
- RUNTIME_SHA_UNCHANGED=YES; ORIGINAL_EVIDENCE_PRESERVED=YES. app.py bbf306ef39cd57c63a09a672624cc243ef58fa99716f15bd78d3c6dbd2dccba3; teddy_mp4_queue.py cb583308c4b3a73b4580fb29dd4d0c63899e3d07fa33561bfc9843fb1ddc7649; teddy_download_safety.py 56c9a868736443fd05ec51b776dd948727d54495296dc254c8dc54fd1fad1ee9 and all recorded preexisting evidence/test bytes are unchanged. Owned temporary test roots are empty after cleanup; bounded child processes exited, no media worker or external service ran.
- PRODUCTION_CHANGED=NO; BUILD=NOT_RUN; DEPLOY=NOT_RUN; DEPLOYMENT_GATE=BLOCKED. Only result documentation is published with historical state fields quoted. No canonical product/test publication, operating Docker/service/task/queue/settings/media/NAS/Stage11/Writer/Gluetun/Selkies/Jellyfin action or dependency installation occurred. Writer participation remains shared-task coordination only. Docker access, latest backup/source manifest, live configuration, Writer socket safety and storage durability blockers remain independent and unresolved.

NEXT_CHECKPOINT: review supported ownership/lifetime of inherited MP4 lock descriptors and separately authorize any minimal runtime correction plus retained negative test. Preserve this failure and stop; do not automatically resume remaining tests, deployment, GANA recovery or legacy job processing.


## SEPARATE USER-APPROVED CHECKPOINT — fork-inherited MP4 lock ownership minimum correction (2026-10-23)

> TASK_ID: DLDWS-001; STATUS: IN_PROGRESS; CONTRACT_VERSION: 1.0.0; REQUIRES_WORKSTREAMS: downloader,discovery-writer-safety.

- AUTHORIZATION: Explicit user approval in current conversation after inherited lock regression FAIL. Scope: review actual lock owner/lifetime at fork boundary; produce minimal **isolated candidate-only** runtime correction in `/tmp/dldws001-mp4-startup-safety-20261022/` and retain/extend the failing negative test; run a narrowly focused offline lock regression. No code publication, Docker build or production action.
- BASELINE: canonical `7d1f0766a5b971511eb4f69afce0d79823f6a6aa`; frozen candidate source prior to change: `app.py` SHA-256 `bbf306ef39cd57c63a09a672624cc243ef58fa99716f15bd78d3c6dbd2dccba3`, `teddy_mp4_queue.py` SHA-256 `cb583308c4b3a73b4580fb29dd4d0c63899e3d07fa33561bfc9843fb1ddc7649`, `teddy_download_safety.py` SHA-256 `56c9a868736443fd05ec51b776dd948727d54495296dc254c8dc54fd1fad1ee9`. Original failure evidence `evidence/remaining-safety-sq81cb50/`; `tests/lock_boundary_checks.py` SHA-256 `58e2259ec6da541778546b014b9055fcbaa2a4d14f5212ca14fbaa10b219a6ce`.
- OBSERVED DEFECT: A child forked from a parent holding actual `InterProcessFileLock` inherits lock object/FD/open-file-description, invokes inherited `release()` without acquiring it itself, and prematurely unlocks the parent's MP4 critical section. The parent remained active while another contender acquired. This is a reproduced inherited-descriptor boundary failure; no operating incident was established.
- MANDATORY PREFLIGHT: confirm actual CT worktree/root/branch/origin/dirty state, all seven shared/workstream governance documents, chosen task and evidence/hash provenance. Inspect actual `InterProcessFileLock`, its users, release/close paths, fork, owner PID handling, context cleanup, reentrant/reacquisition behavior. If a correction changes approved ownership policy or extends into Writer/Stage11/shared resources, stop and request clarification; do not improvise broader design.
- ALLOWED: minimal change in isolated `teddy_download_safety.py` if source review confirms this is the owning implementation, with any needed test-only fixtures in a new evidence location. Enforce that child/nonacquiring process cannot issue `flock(LOCK_UN)` through inherited parent-held state. A child may safely close only its inherited local FD without releasing the parent's lock; verify actual semantics rather than assuming. Preserve same-process acquire/release and context manager/error cleanup; reject inherited acquired state or handle it fail-closed. Retain original failing test as real negative coverage, plus same-process, fresh child-acquire, nonowner/failed-acquire and context-cleanup coverage where safely applicable.
- EXECUTION: record before hashes and original failure; create new uniquely named test evidence; run exactly one focused set of the original four lock tests plus strictly scoped ownership regression after patch; fail-fast on a failure, hidden error or incomplete test path. Do not run the remaining reservation/ENOSPC/ownership/publication/auto-manual-bulk suites, old 13/23/12/11 suites, or real media. Retain before/after source/fixtures SHA-256 and exact test execution counts.
- PROHIBITED: no change to `app.py` or `teddy_mp4_queue.py`, protected preexisting candidate/evidence/worktrees or canonical code; no Docker/Compose build/restart/deploy/socket change, permission bypass, network/package install, GANA/legacy reprocessing, operating tasks/queue/settings/MP4/TS/parts/NAS/Jellyfin; no Writer socket/module/tests, Stage11 or other service modification; no weakening any test or changing governance contracts/router/CI. Writer participation is shared-task coordination only.
- ACCEPTANCE: inherited child `release()` must not open parent's critical section; true owner normal release and subsequent independent contender work; cross-process exclusion; thread serialization, cancel/error cleanup, ownership identity and no unexpected swallowed exception evidence. Report actual PASS/FAIL/INCOMPLETE, changed candidate SHA, retained failure evidence, test counts/hashes and all unresolved gaps. `PRODUCTION_CHANGED=NO; BUILD=NOT_RUN; DEPLOY=NOT_RUN; DEPLOYMENT_GATE=BLOCKED` irrespective of focused outcome.
- NEXT_DECISION: review corrected lock-focused evidence; remaining reservation/ENOSPC/no-clobber/real retry-concurrency tests require separate checkpoint. Docker access, backup/source manifest/live configuration, Writer safety and crash durability remain independent unresolved blockers.


## DLDWS-001 shared-checkpoint coordination — MP4 lock correction result (2026-10-23)

> TASK_ID: DLDWS-001; STATUS: IN_PROGRESS; CONTRACT_VERSION: 1.0.0; REQUIRES_WORKSTREAMS: downloader,discovery-writer-safety.

- This workstream participated only in shared task documentation; no Writer code, test, socket, systemd service or runtime was changed.
- The Downloader candidate's inherited MP4 lock ownership correction passed its focused isolated regression: 6 tests, 6 PASS, 0 FAIL, 0 ERROR, Python 3.10.22. Candidate `teddy_download_safety.py` SHA-256 `8588cf34936aba6936ab943aaa845919a51e8bd68b58e0c2e5ef87e6eecb830d`; no canonical product/test code was published.
- Evidence: `/tmp/dldws001-mp4-startup-safety-20261022/evidence/lock-owner-fix-vhzoco2j/`; result JSON SHA-256 `55a739f9a85c6140c710335caaf8a2c275f0c0897738f77b1bd174ce54015ed9`. The earlier failure record is retained.
- Production changed: NO; build/deploy: NOT_RUN; deployment gate: BLOCKED. Writer socket safety remains unresolved and was not retested or modified.
- Next checkpoint: separately authorize the remaining isolated Downloader reservation/ENOSPC, ownership/publication and retry-concurrency regressions.


## SEPARATE USER-APPROVED CHECKPOINT — remaining isolated MP4 reservation, ownership and retry-race verification (2026-10-23)

> TASK_ID: DLDWS-001; STATUS: IN_PROGRESS; CONTRACT_VERSION: 1.0.0; REQUIRES_WORKSTREAMS: downloader,discovery-writer-safety.

- AUTHORIZATION: Explicit user approval after the fork-inherited lock-owner fix 6/6 focused PASS. This checkpoint authorizes only offline synthetic **verification** of the three remaining Downloader safety areas; no product-runtime modifications, real operation, build or deployment. Writer workstream joins as DLDWS-001 record coordination only; Writer socket/code/tests are untouched.
- CANONICAL_BASE: `939f27595c2d48487be9fa7afddb88f752a55c3b`, branch `teddy-subtitle-stage11`; preserve original user-approved contract/router and historical metadata normalization (only one unquoted current-state header in each ACTIVE_WORK).
- TARGET: isolated candidate `/tmp/dldws001-mp4-startup-safety-20261022/`. Preflight SHA-256: `app.py=bbf306ef39cd57c63a09a672624cc243ef58fa99716f15bd78d3c6dbd2dccba3`, `teddy_mp4_queue.py=cb583308c4b3a73b4580fb29dd4d0c63899e3d07fa33561bfc9843fb1ddc7649`, `teddy_download_safety.py=8588cf34936aba6936ab943aaa845919a51e8bd68b58e0c2e5ef87e6eecb830d` (post lock-fix). Verify prior original failure and lock-fix evidence SHA inventories, test-file lineage and protected working trees before executing.
- PREVIOUS_EVIDENCE: last targeted inherited-lock six-test PASS `evidence/lock-owner-fix-vhzoco2j/result.json` SHA-256 `55a739f9a85c6140c710335caaf8a2c275f0c0897738f77b1bd174ce54015ed9`; original observed lock FAIL `evidence/remaining-safety-sq81cb50/` retained. Prior HLS/yt-dlp 13 groups, startup 23, auth/queue 12, persistence 11 are scoped PASS only, NOT_RERUN. Directory-fsync failure crash-durability still UNKNOWN.
- SCOPE A — RESERVATION/ENOSPC: test actual reservation implementation with independent simultaneous claimants, prevention of oversubscription, bounded reservation release/failure behavior and runtime/admission ENOSPC protection; preserve fragment/partial/output and task-state invariants. Do not fill host disks or alter live tasks/media.
- SCOPE B — OWNERSHIP/NO-CLOBBER/PUBLICATION: test actual result/queue/task ownership identity, conflicting output claimants and existing final file no-overwrite protection; verify checked publication blocks wrong owner, prior-failure, ambiguous, cancellation and target-replacement races at the actual applicable guard. Use synthetic fixture-owned paths and bytes.
- SCOPE C — AUTO/MANUAL/BULK RETRY CONCURRENCY: separately observe real current-runtime admission decisions for each producer and overlaps, not merely mocked dispatch or old BASE_CONTEXT lock/hash checks; prevent duplicate admission, failure-hold bypass, incorrect queue or persistence transitions. Detect unexpected internally caught exceptions and enforce actual path-execution assertions; leave unavailable branches COVERAGE_GAP.
- EXECUTION RULE: map existing relevant tests and reused evidence with read-only review; then run only safe scoped previously-approved offline tests (or minimal new TEST-ONLY isolated fixture/assertions for a clearly demonstrated gap), in staged groups A then B then C, each selected group at most once with fail-fast stop between groups. No broad/all suites or silent retries. Use isolated Python 3.10 environment only if dependency and actual source provenance match; no installation or network bypass. A false green from stubs, skipped guard or caught error is FAIL. No changes to any product runtime, approved original test suite, prior evidence, real service or protected worktree. Fresh unique evidence, before/after SHA-256 inventories, bounded processes, and only fixture-owned cleanup.
- ACCEPTANCE: report `RESERVATION_ENOSPC`, `OWNERSHIP_NO_CLOBBER`, `AUTO_MANUAL_BULK_CONCURRENCY` each PASS/FAIL/INCOMPLETE, and `FAILURE_HOLD`, `LOCK_OWNER_FIX` as reused scoped evidence; actual test counts per group, assertions/path observations, unexpected caught errors, remaining gaps, evidence/result hashes. Any unexpected error/failure/unreachable path blocks next group. `FULL_REGRESSION=PASS` only if all specifically claimed branches were actually verified and no requested coverage gap remains, never conflating prior test PASS with production safety. `PRODUCTION_CHANGED=NO`, `BUILD=NOT_RUN`, `DEPLOY=NOT_RUN`, `DEPLOYMENT_GATE=BLOCKED` regardless.
- PROHIBITED: no Docker build/permission/restart/deploy, real download/remux/FFmpeg, NAS/Jellyfin publication, GANA-3223 or protected legacy-job processing, live task/queue/settings/media/TS/MP4/partial manipulation; no Writer socket/service/test change, Stage11, Gluetun or Selkies change, contract/router/CI change, product-code commit, weakened assertions, cleanup of old evidence/dirty worktrees, forced Git update or automated progression beyond these three test groups.
- NEXT_DECISION: on results, review remaining safety/durability or production-readiness gates separately. No operating action implied by test PASS.

## 2026-10-23 — Remaining MP4 safety regression results

> TASK_ID: DLDWS-001; STATUS: IN_PROGRESS; CONTRACT_VERSION: 1.0.0; REQUIRES_WORKSTREAMS: downloader,discovery-writer-safety.

- This records the separately authorized isolated offline regression checkpoint. It adds no approval, changes no runtime or test code, and makes no production-readiness claim.
- `RESERVATION_ENOSPC=PASS`: group A ran once under Python 3.10.22, 4/4 checks passed. The checks exercised actual candidate reservation/admission and `RemuxTransaction` behavior with synthetic capacity and an injected ENOSPC at the FFmpeg boundary. Reservation release was observed; task memory and test-owned durable state stayed consistent; queue record, fragment, filelist and resume manifest were unchanged.
- `OWNERSHIP_NO_CLOBBER=PASS`: group B ran once, 9/9 checks passed against actual candidate ownership and publication guards. Conflicting claims, existing outputs, wrong task/manifest identity, failed/cancelled/paused/ambiguous states and a final-path race were rejected without changing existing bytes.
- `AUTO_MANUAL_BULK_CONCURRENCY=INCOMPLETE`: group C ran once. Automatic+manual, manual+bulk, and automatic+manual+bulk each admitted the shared job exactly once through observed candidate persistence/queue paths. The fourth failed-job-hold refresh check stopped in its test harness before reaching runtime: `NameError: hashlib is not defined` at `group_c_retry_concurrency.py:190`. Per the fail-fast rule, no test fix or rerun followed.
- `FAILED_JOB_HOLD=PASS` is reused from the prior scoped focused fixture suite (23/23), result `/tmp/dldws001-mp4-startup-safety-20261022/evidence/focused-fixture-retest-91ov7fji/result.json`; it was not rerun here. The current C hold-refresh branch itself remains unverified.
- `LOCK_OWNER_FIX=PASS` is reused from the prior focused lock-owner suite (6/6), result SHA-256 `55a739f9a85c6140c710335caaf8a2c275f0c0897738f77b1bd174ce54015ed9`; it was not rerun here.
- Counts: A 4 run / 4 pass / 0 fail / 0 error; B 9 / 9 / 0 / 0; C 4 checks / 3 pass / 0 assertion failure / 1 harness error. Aggregate: `TESTS_RUN=17`, `PASSES=16`, `FAILURES=0`, `ERRORS=1`. Unexpected caught errors in the three exercised automatic-monitor race paths: 0. The one error was the test harness NameError.
- `FULL_REGRESSION=INCOMPLETE`; `SAFETY_COVERAGE_GAPS`: failed-job-hold current-runtime refresh path was not reached because of the harness error; persistent directory-fsync crash durability remains UNKNOWN. No claim is made beyond the tested branches and reused evidence.
- Frozen candidate runtime SHA-256 before/after was unchanged: `app.py` `bbf306ef39cd57c63a09a672624cc243ef58fa99716f15bd78d3c6dbd2dccba3`; `teddy_mp4_queue.py` `cb583308c4b3a73b4580fb29dd4d0c63899e3d07fa33561bfc9843fb1ddc7649`; `teddy_download_safety.py` `8588cf34936aba6936ab943aaa845919a51e8bd68b58e0c2e5ef87e6eecb830d`.
- `ORIGINAL_EVIDENCE_PRESERVED=YES`; historical failure evidence and prior passing evidence remain unchanged. New evidence directory: `/tmp/dldws001-mp4-remaining-safety-20261023-ptuVzE/`. Aggregate `result.json` SHA-256: `ac606c4e12213a62c355997f2b86fd0088b78c72efa0231a2f2cd3fe858b1ae5`; `coverage.json` SHA-256: `067fe9312ff886df777ed14752552f628058f5d29c90e92887728202fd832c59`.
- Group evidence: A result `3cdab726c328e72b8d8dd29ed9e4e290c6814007eae2ee5ce531211fb7b2a6df`, runner `dfedff5f9ef711610878ed4ddf22d64b6f5f74c798ff9fc3a9599643b0292cfc`; B result `6fde2c6f88d123e25b4398f4098d6bb4a75d72512358a52d1c5b0c69b8566004`, runner `aff86a967756f4426eff0eb28eb48b18c1b09ee7bff160823675933e014d497f`; C result `3cc358e3db9ba17e5788eb36ee2ffc0435e0c1b4660e70c1e6e996a71c09843f`, runner `3a027e941d6062c1836feb3dcf4948d582884f80f3a3f2fb865fb4450a9b9789`.
- `PRODUCTION_CHANGED=NO`; `BUILD=NOT_RUN`; `DEPLOY=NOT_RUN`; `DEPLOYMENT_GATE=BLOCKED`. No real download, operating FFmpeg, Docker/service/task/queue/settings/media, Writer, Stage11, Gluetun, Selkies, NAS or Jellyfin action occurred. Writer remains coordination-only. Docker access, current backup/source-manifest verification, live configuration, Writer socket safety and storage durability remain independent unresolved gates.

NEXT_CHECKPOINT: fix only the isolated test harness's missing `hashlib` import under a separately approved test-only checkpoint, then run only the failed hold-refresh test once if authorized. Preserve all current and historical evidence; do not infer deployment or recovery permission.


## SEPARATE USER-APPROVED CHECKPOINT — one C hold-refresh test-only hashlib repair (2026-10-23)

> TASK_ID: DLDWS-001; STATUS: IN_PROGRESS; CONTRACT_VERSION: 1.0.0; REQUIRES_WORKSTREAMS: downloader,discovery-writer-safety.

- AUTHORIZATION: User explicitly approved only repairing the missing `hashlib` import in the **isolated Group C test harness** and rerunning only the previously interrupted failed-job-hold refresh test once. This is not approval for product-code changes, whole-suite reruns, operational changes, Docker build or deployment. This checkpoint is separately authorized after the prior 16 PASS / 1 harness ERROR report.
- CANONICAL_BASE: `0309a1251ea6ee9237612659250772fec2f816ad`, branch `teddy-subtitle-stage11`, both workstreams DLDWS-001 IN_PROGRESS, contract 1.0.0; retain the normalized historical metadata scheme, governance validator and previous evidence unchanged.
- TARGET: Existing isolated runtime candidate `/tmp/dldws001-mp4-startup-safety-20261022/` and previous Group C evidence `/tmp/dldws001-mp4-remaining-safety-20261023-ptuVzE/`. The prior runtime candidate is frozen: `app.py=bbf306ef39cd57c63a09a672624cc243ef58fa99716f15bd78d3c6dbd2dccba3`; `teddy_mp4_queue.py=cb583308c4b3a73b4580fb29dd4d0c63899e3d07fa33561bfc9843fb1ddc7649`; `teddy_download_safety.py=8588cf34936aba6936ab943aaa845919a51e8bd68b58e0c2e5ef87e6eecb830d`. Original aggregate result SHA-256 `ac606c4e12213a62c355997f2b86fd0088b78c72efa0231a2f2cd3fe858b1ae5`; original Group C runner SHA-256 `3a027e941d6062c1836feb3dcf4948d582884f80f3a3f2fb865fb4450a9b9789`.
- FAILURE TO CORRECT: The fourth Group C failed-job-hold refresh test failed before entering the candidate runtime with harness `NameError: hashlib is not defined` near `group_c_retry_concurrency.py:190`. Earlier A 4/4 and B 9/9 PASS, and C's first three race checks PASS, are retained as prior evidence, not rerun. Prior focused failed-job hold 23-case PASS remains separately scoped; it does not prove this exact current-runtime C refresh route.
- PREFLIGHT: Check real worktree/branch/origin/dirty state, all applicable root/common/workstream AGENTS/contract/ACTIVE_WORK files, exact authorized checkpoint and original evidence/test byte hashes. Read the test's import/reference and chosen test-selector path; verify the error is strictly in the harness. Stop if the actual runtime is the source of the error, if input identity differs, if the test cannot be safely isolated, or if a broader correction is needed.
- ALLOWED: Create a NEW uniquely named fixture/evidence location; copy the original Group C test runner byte-for-byte, then add only the required `hashlib` import or minimal necessary namespace binding. Do not rewrite or weaken the preexisting assertion or other test paths. Check syntactic/AST integrity and explicit selection of ONLY hold-refresh. Execute the single selected failed-job-hold refresh case once in isolated Python 3.10 environment with actual candidate admission, queue, persistence, hold policy and fault detection active. The monitor's unexpected caught exceptions, test-only unrelated producer effects, and unreachable paths must fail the assertion; independently establish actual candidate path reached, failed-job remains held, queue/state/output/fragment bytes unchanged. On failure, error or mismatch, stop without retry. Do not run the other three Group C cases or any other suite.
- PROHIBITED: No changes to frozen product runtime, canonical product/test source, original test/evidence directories, old passing artifacts, protected dirty worktrees, Git contracts/router/CI; no Docker/socket privilege/build/restart/deploy, actual download, GANA-3223 or four historical jobs, FFmpeg/NAS/Jellyfin publishing, operating tasks/queue/settings/media/.parts/TS/MP4, Writer socket/code/tests, Stage11, Gluetun, Selkies, package/network workarounds. Writer workstream participates in shared DLDWS-001 documentation only.
- ACCEPTANCE: `HASHLIB_TEST_FIX`, `HOLD_REFRESH_PATH_REACHED`, `CURRENT_RUNTIME_FAILED_JOB_HOLD`, `UNEXPECTED_CAUGHT_ERRORS`, exact single-case run/pass/error count, before/after three candidate hashes and fixture hashes, original evidence preservation, new result JSON/hash, precise remaining durability gap. Preserve `FULL_REGRESSION=INCOMPLETE` if crash-durability/other coverage is unresolved; `PRODUCTION_CHANGED=NO; BUILD=NOT_RUN; DEPLOY=NOT_RUN; DEPLOYMENT_GATE=BLOCKED` regardless of result.
- NEXT_DECISION: Evaluate this isolated hold-refresh result before separately considering directory-fsync crash durability and remaining operational readiness gates. No automatic follow-on execution or production authorization.

## 2026-10-23 — Group C failed-job-hold refresh single-test result

> TASK_ID: DLDWS-001; STATUS: IN_PROGRESS; CONTRACT_VERSION: 1.0.0; REQUIRES_WORKSTREAMS: downloader,discovery-writer-safety.

- The separately registered checkpoint was verified in both ACTIVE_WORK files at the approval base. Only the isolated Group C test harness copy was changed; no product source was changed.
- `HASHLIB_TEST_FIX=PASS`: source runner SHA-256 `3a027e941d6062c1836feb3dcf4948d582884f80f3a3f2fb865fb4450a9b9789` matched the pinned original. The isolated copy added only `import hashlib`; its SHA-256 is `ca64b4b90d4d9c96ea4aa6c2edcc60d2cca9497e4edef4c8f6806a8b6b36f92a`. Removing the import line recreates the original source. The selected method was syntax-checked before execution.
- Exactly one test ran with Python 3.10.22: `python -m unittest -v group_c_retry_concurrency.RetryConcurrencyGroup.test_04_explicit_failed_mp4_job_is_held_by_startup_admission`. Result: `TESTS_RUN=1`, PASS=0, FAIL=1, ERROR=0; process exit 1. No retry or further test ran.
- `HOLD_REFRESH_PATH_REACHED=YES` for the direct candidate checks: `owns_task_record()` returned true and actual `_eligible_job()` returned no eligible MP4 job; the actual extracted `auto_retry_monitor` was also invoked with the explicit failed MP4 record. Its no-unexpected-caught-error assertion passed. `CURRENT_RUNTIME_FAILED_JOB_HOLD=INCOMPLETE` because the overall test failed before all post-monitor preservation assertions completed.
- `GROUP_C_HOLD_REFRESH=FAIL` as a test result. The failure was an assertion at runner line 216: the test expected the entire synthetic `.tasks.json` byte hash to remain unchanged, but it changed from `dff963982adda95d0fbf86f5767a819e0c60d731032151f3c40a2bae7b30063d` to `0f3fe9b869d7ce0b32fa4e299527aca7cbaa6e8da8952f497a232c4472cbbf35`.
- Static fixture/runtime review identifies the test setup issue: `make_fixture()` inserts an eligible `synthetic-network-error` task before the test adds its explicit failed MP4 task. The real monitor is configured with auto-retry enabled and legitimately persists/enqueues eligible network-error jobs; the state hash assertion therefore observes an unrelated synthetic task transition. The in-memory MP4 failure-record equality assertion immediately before the hash check passed. Assertions after the failing hash comparison—including the queue-file hash and empty-queue checks—did not execute, so those outcomes are not claimed. This failure does not establish a product defect or a complete pass for the MP4 hold path.
- `UNEXPECTED_CAUGHT_ERRORS=0` in the reached monitor invocation. The one test failure was the fixture-wide state-hash assertion, not a hidden exception.
- Runtime SHA-256 remained unchanged: `app.py` `bbf306ef39cd57c63a09a672624cc243ef58fa99716f15bd78d3c6dbd2dccba3`; `teddy_mp4_queue.py` `cb583308c4b3a73b4580fb29dd4d0c63899e3d07fa33561bfc9843fb1ddc7649`; `teddy_download_safety.py` `8588cf34936aba6936ab943aaa845919a51e8bd68b58e0c2e5ef87e6eecb830d`. `ORIGINAL_EVIDENCE_PRESERVED=YES`: prior aggregate result SHA-256 remains `ac606c4e12213a62c355997f2b86fd0088b78c72efa0231a2f2cd3fe858b1ae5`; prior Group C result SHA-256 remains `3cc358e3db9ba17e5788eb36ee2ffc0435e0c1b4660e70c1e6e996a71c09843f`.
- New evidence: `/tmp/dldws001-mp4-hold-refresh-20261023-n7b221km/`; `result.json` SHA-256 `5f6857cbec5085ff039eebeb8553d958266c2580f9c6b79a431019d8b990c54f`; execution log SHA-256 `c5dcbe457599bcbcf234c6cb43295dd8b545a9dbf47f634e0a05958d019b9e1a`.
- `FULL_REGRESSION=INCOMPLETE`; persistent directory-fsync crash durability remains UNKNOWN. `PRODUCTION_CHANGED=NO`; `BUILD=NOT_RUN`; `DEPLOY=NOT_RUN`; `DEPLOYMENT_GATE=BLOCKED`. No live data, service, Docker, media, Writer, Stage11 or other production resource was changed; no test/product code was published.

NEXT_CHECKPOINT: decide whether to separately authorize a test-only fixture-isolation correction and a single rerun of this hold-refresh case. Do not repeat other Group C tests or proceed to production work.


## SEPARATE USER-APPROVED CHECKPOINT — isolated Group C MP4 hold-refresh fixture correction and single retest (2026-10-23)

> TASK_ID: DLDWS-001; STATUS: IN_PROGRESS; CONTRACT_VERSION: 1.0.0; REQUIRES_WORKSTREAMS: downloader,discovery-writer-safety.

- APPROVAL: User explicitly approved a test-only isolation change for the single previously failing Group C failed MP4 job hold-refresh test and precisely one rerun of that selected test. No product runtime or production/build/deploy work is approved.
- BASE: canonical `d019f9669e12b695295fc661055cfc7acbdf4519`, branch `teddy-subtitle-stage11`. Both shared DLDWS-001 workstreams are IN_PROGRESS, contract 1.0.0. This entry adds no new task ID, does not alter contracts/router/CI, and preserves history in quoted fields.
- PREVIOUS FAILURE: Group C selected method `group_c_retry_concurrency.RetryConcurrencyGroup.test_04_explicit_failed_mp4_job_is_held_by_startup_admission` reached real monitor but failed after a synthetic fixture-inserted, *eligible* `synthetic-network-error` task was legitimately retried and mutated the entire temporary `.tasks.json`; pre-existing assertion required byte identity. The failed MP4 memory hold equality had passed, but subsequent queue/state/file assertions were not executed. No product defect is concluded and no prior failure evidence is erased.
- PINNED SOURCE/EVIDENCE: isolated runtime `/tmp/dldws001-mp4-startup-safety-20261022/`; `app.py` SHA-256 `bbf306ef39cd57c63a09a672624cc243ef58fa99716f15bd78d3c6dbd2dccba3`; `teddy_mp4_queue.py` SHA-256 `cb583308c4b3a73b4580fb29dd4d0c63899e3d07fa33561bfc9843fb1ddc7649`; `teddy_download_safety.py` SHA-256 `8588cf34936aba6936ab943aaa845919a51e8bd68b58e0c2e5ef87e6eecb830d`. Prior evidence `/tmp/dldws001-mp4-hold-refresh-20261023-n7b221km/result.json` SHA-256 `5f6857cbec5085ff039eebeb8553d958266c2580f9c6b79a431019d8b990c54f`. Prior test copy with hashlib import SHA-256 `ca64b4b90d4d9c96ea4aa6c2edcc60d2cca9497e4edef4c8f6806a8b6b36f92a`.
- PREFLIGHT: Verify actual worktree/root/branch/origin/dirty state, all required governance docs, approval/readback, SHA invariants, test selector, fixture contents, failing assertion and real monitor source dependencies. Confirm removing/unselecting only the unrelated retryable network-error fixture leaves the MP4 hold-refresh path and expected monitor entry active; otherwise stop BLOCKED rather than relaxing the assertion.
- ALLOWED FIX: Create a NEW separate evidence/test-owned directory, preserve preexisting runner and evidence files byte-for-byte. Copy the previously fixed runner, and modify only the selected hold-refresh test's fixture construction to exclude or make noneligible the unrelated `synthetic-network-error` record without changing production retry semantics; do not change shared fixture behavior for other tests. Prefer an isolated record-set consisting of the explicit failed MP4 record and necessary inert metadata. Preserve all original state-file byte-hash, memory, queue, file, fragment, and error assertions; add only test-only path-reached/invariant observations that protect against a false PASS if appropriate.
- SINGLE EXECUTION: Use same verified Python 3.10 offline isolation; inspect syntax/AST and selected case count before running. Execute only `RetryConcurrencyGroup.test_04_explicit_failed_mp4_job_is_held_by_startup_admission` **ONCE** with real frozen candidate owns_task_record, _eligible_job, auto_retry_monitor, durable persistence and queue decision boundaries. Assert monitor iteration actually executed (not disabled or bypassed), failed MP4 task remains in failed/held state and unqueued, entire test-owned `.tasks.json` and queue bytes remain invariant, fragments/output untouched, no unexpected caught exceptions. Fail-fast on any failure, missing proof, mismatch or unexpected additional producer action. No retries, no other A/B/C cases, no legacy/focused suite runs.
- PROHIBITED: No runtime `app.py`/`teddy_mp4_queue.py`/`teddy_download_safety.py` edits, no canonical product/test code publication, no old evidence/dirty worktree changes, no safety-assertion weakening, no mock of actual monitor/hold/queue/storage safety boundaries; no Docker, permissions, network/packages, deploy/build/restart; no real download, FFmpeg, operating tasks/queue/settings, GANA/legacy jobs, TS/MP4/partials, NAS/Jellyfin, Writer socket/code/tests, Stage11, Gluetun or Selkies actions.
- REPORT: TEST_FIX and TEST_FIXTURE_ISOLATION, HOLD_REFRESH_PATH_REACHED, CURRENT_RUNTIME_FAILED_JOB_HOLD, ONE_TEST_RAN/PASS/FAIL/ERROR, UNEXPECTED_CAUGHT_ERRORS, old/new test hashes, old/result evidence hashes, source before/after hashes and protected file/queue bytes. Preserve prior 16 PASS as historical scope, not rerun. `PRODUCTION_CHANGED=NO; BUILD=NOT_RUN; DEPLOY=NOT_RUN; DEPLOYMENT_GATE=BLOCKED`; `FULL_REGRESSION=INCOMPLETE` while persistent directory-fsync crash durability and independent operational gates remain unverified.
- NEXT_DECISION: Review just this test's new evidence; separately authorize crash-durability or deployment-preflight work if wanted. No automatic progression.

## 2026-10-23 — Group C failed-job-hold refresh isolated single-test result

> TASK_ID: DLDWS-001; STATUS: IN_PROGRESS; CONTRACT_VERSION: 1.0.0; REQUIRES_WORKSTREAMS: downloader,discovery-writer-safety.

- This records the separately approved test-fixture-only correction and exactly one rerun. The prior failure and all prior evidence remain preserved; no product/runtime code or canonical test code was changed or published.
- `FIXTURE_ISOLATION=PASS`: A new test-owned copy of the previously corrected runner changed only the selected test fixture to exclude the unrelated retryable synthetic network-error job. The shared fixture and other three Group C test bodies were unchanged. A synthetic fragment and pre-existing output sentinel were included to check preservation.
- `HOLD_REFRESH_PATH_REACHED=YES`: The real extracted `auto_retry_monitor` completed exactly one scan iteration; candidate `owns_task_record` returned true and candidate `_eligible_job` returned no eligible job for the explicit failed MP4 record. The held MP4 job was not enqueued.
- `CURRENT_RUNTIME_FAILED_JOB_HOLD=PASS` for this single isolated candidate test. Existing assertions passed for the failed job's in-memory record, full `.tasks.json` bytes, queue-record bytes, empty runtime download queue, no persistence commits, and unchanged fragment/output sentinel hashes.
- `STATE_FILE_UNCHANGED=YES`; `QUEUE_UNCHANGED=YES`; `FRAGMENTS_UNCHANGED=YES`; `UNEXPECTED_CAUGHT_ERRORS=0`.
- Exactly one test ran under Python 3.10.22 using `python -m unittest -v group_c_retry_concurrency.RetryConcurrencyGroup.test_04_explicit_failed_mp4_job_is_held_by_startup_admission`: `TESTS_RUN=1`, PASS=1, FAIL=0, ERROR=0, exit code 0.
- Test copy: `/tmp/dldws001-mp4-hold-refresh-isolated-20261023-cucg7uti/tests/group_c_retry_concurrency.py`, SHA-256 `5e19f59c41cbca0d70684b958e3769fac7d1f964f0db1da1c24a4740b6f27d30`. It was copied from the prior runner SHA `ca64b4b90d4d9c96ea4aa6c2edcc60d2cca9497e4edef4c8f6806a8b6b36f92a`. Evidence `result.json` SHA-256 `1d65228213d6c2d05f9b605e4206b08b00e4039a947c39fade03e040ea16d044`; log SHA-256 `f62abf823fe6c1c2b916fdbe0426c72f6b7b3c164c989edadfc78a57950ddc56`.
- Frozen runtime SHA-256 remained unchanged: `app.py` `bbf306ef39cd57c63a09a672624cc243ef58fa99716f15bd78d3c6dbd2dccba3`; `teddy_mp4_queue.py` `cb583308c4b3a73b4580fb29dd4d0c63899e3d07fa33561bfc9843fb1ddc7649`; `teddy_download_safety.py` `8588cf34936aba6936ab943aaa845919a51e8bd68b58e0c2e5ef87e6eecb830d`. `ORIGINAL_EVIDENCE_PRESERVED=YES`, including the prior failed result SHA-256 `5f6857cbec5085ff039eebeb8553d958266c2580f9c6b79a431019d8b990c54f`.
- `FULL_REGRESSION=INCOMPLETE`: persistent directory-fsync crash durability and independent operational-readiness gates remain unverified. `PRODUCTION_CHANGED=NO`; `BUILD=NOT_RUN`; `DEPLOY=NOT_RUN`; `DEPLOYMENT_GATE=BLOCKED`. No further tests or operational actions were performed.



## SEPARATE USER-APPROVED CHECKPOINT — isolated directory-fsync failure and crash-durability investigation (2026-10-23)

> TASK_ID: DLDWS-001; STATUS: IN_PROGRESS; CONTRACT_VERSION: 1.0.0; REQUIRES_WORKSTREAMS: downloader,discovery-writer-safety.

- APPROVAL: User explicitly authorized only isolated investigation and verification of persistent **directory fsync failure / crash durability** after completion of the 1/1 failed-job hold-refresh test. Do not infer approval for implementation fixes, runtime changes, hardware power interruption, production build/deploy or live state manipulation. This checkpoint remains a shared DLDWS-001 documentation task; Writer participation is coordination only, not Writer socket testing.
- BASE: repository `ssikgun/missav-dlp-web`, canonical branch `teddy-subtitle-stage11`, base commit `070f2844d9f5b9b87316aaed51148a9a68c9955f`. Preserve common/workstream approved contracts, routing registry, existing active task IDs/status and normalized historical metadata.
- TARGET: isolated current MP4 candidate `/tmp/dldws001-mp4-startup-safety-20261022/`; frozen `app.py` SHA-256 `bbf306ef39cd57c63a09a672624cc243ef58fa99716f15bd78d3c6dbd2dccba3`, `teddy_mp4_queue.py` SHA-256 `cb583308c4b3a73b4580fb29dd4d0c63899e3d07fa33561bfc9843fb1ddc7649`, `teddy_download_safety.py` SHA-256 `8588cf34936aba6936ab943aaa845919a51e8bd68b58e0c2e5ef87e6eecb830d`. Exact existing persistence 11-case evidence `/tmp/dldws001-mp4-startup-safety-20261022/evidence/persistence-repair-3_smdk0f/` recorded result SHA-256 `db0926d46237764084f5905f23d3b9e369298835a710831e251ce844c4bc1677`; latest hold-refresh evidence `/tmp/dldws001-mp4-hold-refresh-isolated-20261023-cucg7uti/result.json` SHA-256 `1d65228213d6c2d05f9b605e4206b08b00e4039a947c39fade03e040ea16d044`.
- KNOWN GAP: earlier injected failure of directory `fsync` in state persistence rejected admission and restored prior observable in-process task/file/queue state, but **post-power-loss directory entry durability is UNKNOWN**. Successful Python unittest/assertion and a process kill cannot by themselves prove persistence across true power loss or storage controller/cache failure.
- PREFLIGHT: Confirm physical working directory, Git root/branch/origin/current remote SHA/dirty files; read root AGENTS, common contract/routing, downloader and discovery-writer-safety contracts/active files and relevant current handoff. Check source/before hashes, old evidence preservation, concrete persistence implementation and test coverage (temp write, data fd fsync, atomic replace, directory fd fsync, cleanup/rollback) before selecting new work. Confirm test ownership and non-interference. If safe isolation, exact source provenance or authorization fails, stop with BLOCKED, not an improvisational workaround.
- ALLOWED READ-ONLY ANALYSIS: map real failure point(s), ordering/durable transaction boundaries and established guarantees for the current candidate; identify whether failures can leave old/new/missing/corrupt state, orphan temp files or inconsistent queue/ownership; distinguish app-level rollback, process crash, OS crash, storage crash, and actual power loss. Use existing 11-case evidence; do not rerun passing suites.
- ALLOWED LIMITED TEST: only if analysis identifies a concrete untested property, add **test-only** isolated synthetic fixture(s) under a fresh unique evidence dir and execute the minimum scoped cases **once per approved selected case/group**, with fail-fast on first unexpected failure. May simulate fsync OSError, partial durable commits, restart/reload of test-owned state, and bounded disposable child-process termination (only after demonstrating no real service or protected files involved); no real power off/reboot, live filesystem unmount, host signal, disk exhaustion, storage fault injection or production crash. Use actual candidate persistence code/decisions; do not mock the safety decision or falsely claim disk persistence from test stubs. Record actual calls reached, exceptions propagated or rejected, file bytes and SHA state/queue/fragment before/after, and orphan temp state. Do not silently swallow unknown exceptions.
- PROHIBITED: no product code changes, canonical product/test publication, original fixture/evidence modification, broad old suites (13/23/12/11/6/17), actual downloads, FFmpeg, Docker/Compose build/deploy/restart/permission work, host stop/reboot/power cycle, operating task/queue/settings/media/NAS/Jellyfin/partial/MP4/TS operations, GANA-3223 or historical jobs, Writer socket/code/test/services, Stage11, Gluetun, Selkies, packages/network workarounds, governance router/contract/CI changes. No cleanup of pre-existing or dirty user files; only new test-owned assets subject to evidence-preserving cleanup.
- ACCEPTANCE: Explicitly classify `DIRECTORY_FSYNC_FAULT_PATH`, `IN_PROCESS_ROLLBACK`, `PROCESS_RESTART_RECOVERY`, `CRASH_DURABILITY`, `QUEUE_STATE_CONSISTENCY`, `PROTECTED_BYTES_PRESERVED`, each PASS/FAIL/INCOMPLETE/UNKNOWN **according to precisely exercised failure model**. Include one-page failure-window matrix, actual test count and logs, hashes and failure path observers, residual uncertainty, any concrete product defect, and minimally scoped proposal (not implementation) if needed. Process-level/fixture PASS must not yield power-loss `CRASH_DURABILITY=PASS`; classify UNKNOWN if unprovable. Retain prior green results as historical, do not inflate `FULL_REGRESSION`. Product/runtime SHA unchanged and all previous evidence retained; `PRODUCTION_CHANGED=NO; BUILD=NOT_RUN; DEPLOY=NOT_RUN; DEPLOYMENT_GATE=BLOCKED` irrespective of outcome.
- NEXT_DECISION: Review findings to choose whether a separate minimally scoped correction/verification or an operational preflight is necessary. No automatic follow-on, product publishing, build or deployment.


## 2026-10-23 — DLDWS-001 directory fsync fault/reload verification result

> TASK_ID: DLDWS-001; STATUS: IN_PROGRESS; CONTRACT_VERSION: 1.0.0; REQUIRES_WORKSTREAMS: downloader,discovery-writer-safety.

- REVIEW: The frozen retry transaction stages and verifies a same-directory temporary state file, fsyncs file data, preserves the prior inode through a recovery hard link, atomically replaces the task file, fsyncs its parent directory, then admits to the in-memory download queue. On failure after replacement it restores the in-memory task and attempts to restore the prior file; uncertain rollback returns a manual-reconciliation error and refuses queue admission. General save_tasks() remains a separate non-fsync path and was not changed.
- DIRECTORY_FSYNC_FAULT_PATH=PASS; IN_PROCESS_ROLLBACK=PASS for observable memory/bytes/inode; PROCESS_RESTART_RECOVERY=PASS for a fresh Python process loading the same live filesystem; CRASH_DURABILITY=UNKNOWN.
- QUEUE_STATE_CONSISTENCY=INCOMPLETE: the synthetic in-memory download queue remained empty; no pre-existing durable MP4 journal was included in this new failure fixture. Prior failed-job hold evidence is retained separately.
- PROTECTED_BYTES_PRESERVED=YES for the synthetic task file, fragment, existing-output sentinel, and prior evidence. No retry temporary file remained. TESTS_RUN=1, PASS=1, FAIL=0, ERROR=0, UNEXPECTED_CAUGHT_ERRORS=0. The three frozen runtime SHA-256 values remained unchanged.
- FULL_REGRESSION=INCOMPLETE; prior persistence 11/11 and failed-job-hold 1/1 results were reused, not repeated. CRASH_DURABILITY remains UNKNOWN; first parent-directory fsync after recovery-link creation, unlink-failure cleanup, and a present MP4 journal in this exact fault scenario remain coverage gaps.
- PRODUCTION_CHANGED=NO; BUILD=NOT_RUN; DEPLOY=NOT_RUN; DEPLOYMENT_GATE=BLOCKED. No product/test source or service was changed.
- EVIDENCE: `/tmp/dldws001-mp4-fsync-restart-20261023-xly07iqy/`; test SHA-256 `9aed6a42b45763ef56e53208ead3da85a8669a219601824381400555d4d016dd`; result SHA-256 `eea8f64d323373ee120c2aa25db691a8350cad6bf4fd289e636b7d51cb74ff42`; failure-window matrix SHA-256 `865cbd3286a1a3ae9bf8d35f8b3dca392f9e341d45b5c0dead5ff4f3010056e0`.
- NEXT: No automatic progression. True post-power-loss durability and any product change require separate review/approval.


## SEPARATE USER-APPROVED CHECKPOINT — isolated generic save_tasks atomic persistence correction and focused tests (2026-10-23)

> TASK_ID: DLDWS-001; STATUS: IN_PROGRESS; CONTRACT_VERSION: 1.0.0; REQUIRES_WORKSTREAMS: downloader,discovery-writer-safety.

- USER AUTHORIZATION: After the isolated directory-fsync fault/restart report the user explicitly approved **minimum isolated-candidate correction of general `app.py save_tasks()` persistence plus focused offline regression**, with no canonical product-code publication or live deployment. This authorizes source changes in an isolated candidate and necessary test-only fixtures only; it does not authorize changes to existing workstream contracts/design, production, original evidence, Writer socket/code, Stage11, or other assets.
- BASE/PROVENANCE: `ssikgun/missav-dlp-web` canonical `teddy-subtitle-stage11` head `1446fbb464404e256b5d6587dfa02e689cab3ab7`. Root `AGENTS.md`, common contract/router, downloader and discovery-writer-safety active contracts v1.0.0 and shared DLDWS-001 must be checked against the current remote head and actual local worktree before work. Read relevant CURRENT_HANDOFF. Preserve historical approval/failure evidence and exactly one set of unquoted ACTIVE_WORK metadata fields.
- FROZEN INPUT: isolated candidate `/tmp/dldws001-mp4-startup-safety-20261022/`, verify candidate `app.py` SHA-256 `bbf306ef39cd57c63a09a672624cc243ef58fa99716f15bd78d3c6dbd2dccba3`, `teddy_mp4_queue.py` `cb583308c4b3a73b4580fb29dd4d0c63899e3d07fa33561bfc9843fb1ddc7649`, `teddy_download_safety.py` `8588cf34936aba6936ab943aaa845919a51e8bd68b58e0c2e5ef87e6eecb830d`. The canonical `app.py` around the `save_tasks()` definition uses `open(TASKS_FILE, 'w')`, `json.dump()` and broad swallowed `Exception`, and is called by load/start/success/cancel/error/auto-retry/manual-retry/create/delete. Confirm isolated candidate behavior and call-site paths instead of assuming canonical is byte-identical.
- OBJECTIVE: Preserve the existing task JSON format and workflow while replacing unsafe truncate-and-silent-write with checked atomic same-directory persistence, as much as possible reusing verified existing transactional/safe-write helpers without circular imports or collision with existing queue admission. Surface failures to the relevant caller; no silent success or queue enqueue after a failed required durability write. Preserve explicit failed MP4 hold, ownership, global MP4 lock, no-clobber, resume and cancellation boundaries. Do not alter configured concurrency or change ordinary operation except necessary failure handling.
- MANDATORY READ-ONLY DESIGN/PREFLIGHT: inspect real `save_tasks` and every call site under current candidate, `load_tasks` and retry monitor, lock ordering (`_tasks_lock`, `queue_admission_lock`, disk/MP4 locks), existing safe persistence helper and dependency structure; map file/directory write, flush, fsync, replace, cleanup, status rollback/admission semantics. If a correctness-preserving fix requires a broader queue/state or task ownership policy change, conflicts with the contract, or crosses protected Writer/Stage11 scope, stop and report proposed alternatives for user decision; do not silently implement a redesign.
- ALLOWED IMPLEMENTATION: change only the isolated candidate copy of `app.py` and freshly created isolated TEST-ONLY fixtures necessary to verify a narrowly scoped `save_tasks()` correction; touch another product file only if separately authorized. Use temp file in same directory, JSON-serialize without truncating the live file, verify flush/file fsync, atomic replace and parent-directory fsync, preserve existing path/permissions where required and protect preexisting output. Failed writes must be reported/propagated or safely handled and must not falsely return task/queue admission success; classify post-replace uncertain durability as UNKNOWN/manual reconciliation where necessary rather than asserting rollback certainty. Do not weaken guards or swallow errors.
- FOCUSED TESTING: create new evidence directory, record exact hashes and protected inventories before and after. With test-owned paths/queue/state, check successful save/load, serialization and open/partial-write/flush/file fsync/replace/directory fsync failures, ENOSPC, preservation of previously valid .tasks.json, no stray temp files, checked error propagation, failure/paused/cancelled states and queue-admission order; actual paths must execute, exceptions must not be hidden. Examine targeted concurrent saves and lock ordering if safely possible. Use minimum selected isolated tests once per selected test/group with fail-fast; do NOT rerun prior 13/23/12/11/6/17 grouped suites or real downloads. A process-reload PASS is not power-loss durability PASS.
- PROHIBITIONS: no canonical product/test commit; no changes to `teddy_mp4_queue.py`, `teddy_download_safety.py`, existing protected candidate files/evidence aside from the explicitly allowed isolated app.py, or original failures; no live Docker/Compose/build/deploy/restart/socket permission, actual media/download/NAS/Jellyfin work, GANA or legacy-job retry, real tasks/queue/settings/TS/MP4/parts mutation, Writer socket/code/test/services, Stage11, Gluetun, Selkies, new packages/network bypass, governance contract/router/CI edits, broad cleanup. Writer participation is shared-task coordination only.
- ACCEPTANCE/REPORT: `SAVE_TASKS_ATOMIC_FIX`, `SAVE_FAILURE_PROPAGATION`, `QUEUE_ADMISSION_ON_PERSISTENCE_FAILURE`, `EXISTING_BYTES_PRESERVED`, `NORMAL_SAVE_LOAD`, `FOCUSED_REGRESSION`, run/pass/fail/error counts, unexpected swallowed exceptions, all observed paths and remaining gaps, before/after candidate app.py SHA-256, untouched queue and safety module SHA, prior evidence preservation, new evidence/result JSON and hash. Clearly distinguish proven process/in-process behavior from `CRASH_DURABILITY=UNKNOWN` and remaining durable MP4 journal gap; do not declare full regression or production readiness based on a focused PASS. `PRODUCTION_CHANGED=NO; BUILD=NOT_RUN; DEPLOY=NOT_RUN; DEPLOYMENT_GATE=BLOCKED` regardless.
- NEXT_DECISION: Review narrow candidate fix and focused results; separately authorize any additional product implementation, canonical source publication, operational preflight or deployment. No automatic next step.
## 2026-10-23 — DLDWS-001 general task-state save atomicity isolated result

> TASK_ID: DLDWS-001; STATUS: IN_PROGRESS; CONTRACT_VERSION: 1.0.0; REQUIRES_WORKSTREAMS: downloader,discovery-writer-safety.

- The separately approved checkpoint changed only the isolated candidate `/tmp/dldws001-mp4-startup-safety-20261022/app.py`; no canonical product/test code was published. The candidate now serializes before touching the live state file, stages and fsyncs a same-directory temporary file, preserves the prior file by verified hard link, atomically replaces, verifies readback, fsyncs the directory, and attempts restoration on post-replace failure. Persistence exceptions propagate instead of being silently swallowed.
- `SAVE_TASKS_ATOMIC_FIX=PASS`; `SAVE_FAILURE_PROPAGATION=PASS`; `EXISTING_BYTES_PRESERVED=YES`; `NORMAL_SAVE_LOAD=PASS`. Fault injection reached serialization, temp open, partial write, ENOSPC write, flush, regular-file fsync, first directory fsync, pre-rename replace, replace-reported-after-rename, and post-replace directory-fsync paths. Existing bytes/inode and the test-owned output sentinel remained unchanged for failed saves; owned temp/backup names were absent after recoverable failures.
- `QUEUE_ADMISSION_ON_PERSISTENCE_FAILURE=PASS` for the actual candidate `teddy_routing.enqueue_download` function and statically reviewed resume path: a save exception stopped control before queue insertion and no success response was returned. The failed new-download request did leave its newly created `대기 중` record in volatile memory while the durable file stayed unchanged and the queue remained empty; this is recoverable on process reload but can appear as a stuck task until reconciliation. The isolated correction does not roll back every caller's earlier in-memory mutation; broader call-site transaction handling remains a separate review item.
- Thread-level concurrent saves (two writers) produced one valid complete JSON state without deadlock. `_tasks_lock` ordering was retained; explicit and automatic retries still use the existing `persist_retry_state_and_enqueue` transaction and were not changed.
- `TESTS_RUN=13 / PASSES=13 / FAILURES=0 / ERRORS=0`; `UNEXPECTED_CAUGHT_ERRORS=0`. Existing historical suites were not rerun. `CRASH_DURABILITY=UNKNOWN`; `FULL_REGRESSION=INCOMPLETE` because this was a focused candidate suite, and process/host crash durability, directory-entry persistence after physical power loss, and broader worker failure behavior were not tested.
- Candidate runtime SHA-256: `app.py=f2ffdc1542f1203e7c533bf0116d617bb9f7d2a9d9fb937455b75f17d640244e`; unchanged `teddy_mp4_queue.py=cb583308c4b3a73b4580fb29dd4d0c63899e3d07fa33561bfc9843fb1ddc7649`; unchanged `teddy_download_safety.py=8588cf34936aba6936ab943aaa845919a51e8bd68b58e0c2e5ef87e6eecb830d`. All 94 pre-existing evidence files remained hash-identical (manifest SHA-256 `64c6266f73e66a55e83b1be978538879af1cf0e87b9c4c9ffbe7a0b3cdf76398`). Evidence: `/tmp/dldws001-save-tasks-atomic-20261023-1nt7i1km/`; test SHA-256 `6dec82d47a68fc5270548966cb5e7b142c85c6cab04f62a8c64e065712f0ff90`; result SHA-256 `b3717c4aea5067abaeb4524223b461c8adc56b676ba803eeaafdafa348aeb9cd`; final evidence SHA-256 `deda4efe4278c936befbac3ae0f451833e9c648876feeda8de7b6d9593561a10`.
- `PRODUCTION_CHANGED=NO`; `BUILD=NOT_RUN`; `DEPLOY=NOT_RUN`; `DEPLOYMENT_GATE=BLOCKED`. No Docker, production task/data, Writer, Stage11, or external media service was touched. This candidate PASS is not operational readiness or canonical publication.
- NEXT_DECISION: Review the volatile-task-on-save-failure limitation and focused candidate diff; separately authorize any caller-level rollback work, further tests, canonical publication, or operational action.


## USER-APPROVED URGENT CHECKPOINT — diagnose live MP4/NAS pipeline regression read-only (2026-10-23)

> TASK_ID: DLDWS-001; STATUS: IN_PROGRESS; CONTRACT_VERSION: 1.0.0; REQUIRES_WORKSTREAMS: downloader,discovery-writer-safety.

- USER INTENT: Restore previously working download→serialized one-at-a-time MP4 conversion→NAS publication urgently after widespread failure affecting new jobs; user authorized urgent action/requested resolution, but this checkpoint authorizes only **read-only causal diagnosis and preparation of an exact recovery plan**. It does NOT authorize production deployment/restart, task-state edits, existing-job replay, NAS changes, Docker socket/privilege bypass, fixes outside separately approved isolated patches, or destructive recovery. Do not misinterpret urgent wording as overriding earlier explicit safety boundaries.
- CANONICAL: `ssikgun/missav-dlp-web`, branch `teddy-subtitle-stage11`, preapproval head `e9981e7bc22485560adf97efb7b6d11b6b52ae49`, DLDWS-001 shared across downloader and discovery-writer-safety, contracts 1.0.0. Root AGENTS, common contract/router, both selected contracts/ACTIVE_WORK and relevant CURRENT_HANDOFF must be confirmed at the latest SHA; verify actual local pwd/root/branch/origin/dirty state. Historical NEXT entries are not approval.
- VERIFIED LEAD: Prior live investigation of GANA-3223 on observed image `sha256:7200290e8af11d9f253a5efd028bf3be2a2757af9049f0bb9e43bd04f821f2d8` showed the actual HLS MP4 (~2,353,735,715 bytes, ffprobe PASS) existed but `_complete_job()` called `_local_outputs()` and wrongly required a missing `.<task_id>.ytdlp-home` folder. A minimal isolated fix at `/tmp/dldws001-gana3223-hls-result-fix-20261022/teddy_mp4_queue.py`, SHA-256 `593b3ad77f50e2af64589d84a005fad5ce79495e4280011f3e240a6961ba9730`, previously passed 13 offline smoke groups. It was not published or deployed. DO NOT infer other new jobs failed for the identical reason absent per-job evidence.
- OTHER LEADS: On 2026-10-20 one Downloader-only production deployment of image `sha256:83322ee82e736b5ba026b8d98d5709b9685ca9c6b051c2a7f4c7b9bf8d058573` was recorded; REAL_DOWNLOAD_TEST=NOT_RUN and REAL_MP4_TEST=NOT_RUN. Later live image was observed as `7200290e...` but freshness unknown. On 2026-10-22 later overlay rollout was BLOCKED by Docker API permission denied, missing current backup/manifest/live Compose and Writer safety evidence. GANA's failed task versus sealed `output_ready` MP4 queue record can trigger unsafe automatic startup replay. Old four ENOSPC errors are separate and require preservation.
- READ-ONLY FIRST: Via actual authorized Proxmox/CT108 operator context (never assume Codex LXC has Docker access), verify exact CT identity and Docker daemon permissions without bypass; inspect `missav-dlp-web` live container/image/config identity; recent relevant MP4-stage/queue/NAS logs with credential, URL and token redaction; bounded task IDs/status/mp4_queue_kind/stage/local_result presence, queued/running/failed counts; sealed queue job stages for the GANA case and a representative NEW affected job; disk capacity/inodes and global MP4 lock/worker liveness without altering locks; whether a validated MP4 is local and whether NAS publication is blocked. Preserve current `.tasks.json`, queue journal, MP4, TS, .parts and any old GANA outputs exactly. Distinguish missing/inaccessible Docker from application errors; never claim current runtime provenance from old snapshots.
- DIAGNOSE: Produce a one-screen chain showing for at least one new failure: download completed? input fragments intact? conversion attempted? local MP4 generated/validated? `_complete_job` result collection failed? NAS publication attempted? Determine whether the same HLS/ytdlp-home defect applies, or if separate capacity, lock, output ownership, recovery, network or NAS blocker exists. Clearly separate proven facts from hypotheses and partial evidence. Identify minimal patch set (prefer already-tested HLS-only change) and *exact operational gates* needed for safe user-approved rollout, including backup and GANA startup replay handling. No speculative rewrite.
- PROHIBITED: No Docker builds/up/down/restart, `docker exec` changes, task requeue/auto-retry operations, app/queue/settings/media/NAS/Jellyfin edits, GANA/legacy recovery, service reload, permission escalation, socket chmod/chown, removing lock files, altering Writer/Stage11/Gluetun/Selkies, product-code canonical publication or changing contracts/router/governance CI. Existing isolated candidate evidence remains immutable. If Docker access is denied, record blocker and request the minimal READ-ONLY operator output rather than looping or bypassing.
- REPORT: `CURRENT_LIVE_IMAGE`, `LIVE_DOCKER_ACCESS`, `NEW_JOB_FAILURE_CHAIN`, `HLS_OUTPUT_BUG_IN_LIVE=YES/NO/UNKNOWN`, `GANA_STARTUP_REPLAY_RISK`, `MP4_LOCK_STATE`, `NAS_PUBLISH_STATE`, `DISK_CAPACITY`, `PATCH_ALREADY_TESTED`, and `NEXT_SAFE_OPERATION`. Count examined jobs and source evidence. `OPERATING_WRITES=NO; BUILD=NOT_RUN; DEPLOY=NOT_RUN` unless a separate user-approved execution checkpoint is registered in all affected workstreams. Do not postpone with additional unrelated unit tests.
- NEXT_DECISION: Immediately present concise evidence-based resolution proposal (minimal patch/image build/isolated preflight, controlled startup replay handling and one harmless user-approved fresh job E2E verification) for separate explicit deployment/recovery authorization. Do not claim this read-only task repairs operations.


## SEPARATE USER APPROVAL — GANA-3223 validated existing-MP4 completion and NAS publication (2026-10-23)

> TASK_ID: DLDWS-001; STATUS: IN_PROGRESS; CONTRACT_VERSION: 1.0.0; REQUIRES_WORKSTREAMS: downloader,discovery-writer-safety.

- USER DECISION: The user explicitly approved **GANA-3223 ONLY**: verify its **already-produced** MP4 and, once verified safe, finish that existing job normally and publish its validated artifact to NAS, without redownloading or removing the original local MP4/TS/fragments. User urgently wants the download→one-at-a-time MP4→NAS pipeline restored. This one-job publication approval does NOT approve processing the four earlier failed jobs, publishing unverified artifacts, resetting/recreating an image/container, arbitrary retrying, modifying Writer/Stage11, overriding an existing NAS target, deleting local files or ignoring existing deployment gates. Do not confuse this with an unconditional deployment approval.
- IDENTITY / BASIS: user-visible item `GANA-3223`, task UUID `088a91a7-701f-45d1-a38e-5e1c92cd1f56`, current task error `mp4_stage=failed`, `mp4_queue_kind=hls`, no local result path. In live CT108 read-only operator evidence on 2026-10-23, `missav-dlp-web` image `sha256:7200290e8af11d9f253a5efd028bf3be2a2757af9049f0bb9e43bd04f821f2d8` running with no restart; mounted host and container `.tasks.json` SHA-256 `b287727a103c6b44a99aebf2394efa1af59a990a834caf584787eb664ef1657a`, last mtime 2026-10-22 18:59:50 KST. Exactly five failed tasks; four older tasks protected, GANA last. The `.teddy-mp4-queue` directory has one 173206-byte sealed HLS record in `output_ready` with mtime 2026-10-22 18:59:50 KST; attempt directory contains zero files, no active ffmpeg shown. These facts do not themselves prove queue/task identity or whole-MP4 integrity. Host filesystem ~25 GB available. Protect all protected assets unchanged until the preflight actually proves safety.
- ROOT CAUSE AND AVAILABLE FIX: Previous read-only investigation attributed GANA failure after a completed HLS MP4 (2,353,735,715-byte, ffprobe PASS on 2026-10-22) to `_complete_job` expecting nonexistent `.<task_id>.ytdlp-home` for HLS. Frozen isolated HLS-only fix: `/tmp/dldws001-gana3223-hls-result-fix-20261022/teddy_mp4_queue.py`, SHA-256 `593b3ad77f50e2af64589d84a005fad5ce79495e4280011f3e240a6961ba9730`, 13 offline smoke groups PASS; not deployed, and not full real-media/production proof. Actual 2026-10-23 operator container image remains old.
- SAFE GATES BEFORE ANY WRITE: Verify true CT108 Docker identity/live image/code fingerprint and the currently loaded queue worker, exact SHA and identity binding among UUID/task, sealed HLS journal, output path and on-disk file, no symlinks/escape, hash/size/ffprobe/media consistency and source fragment retention, output-stage/ownership/lock validity, no concurrent media handling. Inspect NAS configured destination through existing authorized read-only access: target absence, no same-name or same-content collision, no pre-existing partial/complete target or other title owner, capacity/permissions and final publication semantics. Verify baseline backup/restoration strategy that preserves all *current* state after 2026-10-20 and live Writer/Compose compatibility and image rollback as applicable; never rely on stale pre-GANA backup alone. If source video validation or exact target mapping fails, stop BLOCKED; no blind `scp`, `mv`, manual database/status edits, or fabricated completion marker.
- STARTUP HAZARD: The current failed task vs sealed queue `output_ready` record is known to be replay-eligible at container startup. Therefore do not restart/redeploy even just to apply the HLS fix unless a separately approved exact one-job startup-recovery control demonstrably prevents *any* unauthorized GANA or older-task processing, covers preservation/integrity and passes all operational preflight gates. Do not assume stopping or renaming the journal is safe. Writer socket, Gluetun, Selkies and Stage11 remain protected.
- CONDITIONAL AUTHORIZED ENDPOINT: After all gates PASS and a safe verified normal pipeline route is established, a **single** no-overwrite NAS final publication and matching verified GANA completion-state transition is approved. Any process that cannot isolate this exact artifact and guarantee other jobs unaffected must stop and report a precise additional approval/implementation requirement. No forced converter rerun, duplicate file, cleanup/partial deletion or extra NAS writes. File/source fragments and original existing MP4 remain protected until final verified NAS readback and explicit separately approved cleanup.
- NOW: Read-only preflight of sealed JSON identifiers/paths/ownership, current MP4 and NAS target, live pipeline and backup evidence; do not execute a mutation on guesswork. If full validation needs expensive full content hashing/stream decoding, use only test-owned read operations and report confidence boundaries; no source modifications. Distinguish what was verified previously from live re-verification. HLS correction and selective startup replay changes require separate explicit implementation/release approval if not already provided for that exact operation; never silently broaden this one-target publication decision to a general image rollout.
- ACCEPTANCE: `GANA_TASK_QUEUE_BINDING=PASS/FAIL/UNKNOWN`, `GANA_MP4_INTEGRITY=PASS/FAIL/INCOMPLETE`, `NAS_TARGET_NO_CLOBBER=PASS/FAIL/UNKNOWN`, `STARTUP_REPLAY_SAFETY=PASS/FAIL/UNKNOWN`, `BACKUP_AND_ROLLBACK_READY=PASS/FAIL/INCOMPLETE`; only if all necessary gates pass and actual authorized one-shot operation is performed, report `GANA_NAS_PUBLISHED=PASS`, preserved old local bytes and final task state/recipient readback. Otherwise `GANA_NAS_PUBLISHED=NOT_RUN`, explain blocker. `DEPLOY=NOT_RUN` until separate release authorization. Keep other four failures, live downloads, stage11, Writer, Gluetun, Selkies untouched.
- NEXT_DECISION: Choose the smallest verified runtime correction and startup control needed to enable the specifically approved GANA publication, and verify one new real download→MP4→NAS path under a separately approved safe operating canary. No auto-progression from documentation or synthetic tests.


## EXECUTION RESULT — DLDWS-001 GANA-3223 safe recovery preflight (2026-10-23)

- `GANA_RECOVERY_PREFLIGHT=BLOCKED`; `NAS_NO_CLOBBER=INCOMPLETE`; `LOCAL_MP4_PRESERVED=YES` and `FRAGMENTS_PRESERVED=YES` only as “Codex made no writes” (no live re-read); `TASK_QUEUE_CONSISTENCY=BLOCKED`; `STARTUP_REPLAY_SAFETY=BLOCKED`; `GANA_NAS_PUBLISHED=NOT_RUN`; `NORMAL_NEW_DOWNLOAD_PIPELINE=INCOMPLETE`; `PRODUCTION_CHANGED=NO` (no Codex production action; live state not rechecked); `BUILD=NOT_RUN`; `DEPLOY=NOT_RUN`.
- Source review used only the preserved 2026-10-22 operator snapshot, not a live CT108 connection. The old queue code's HLS `_local_outputs()` requires the absent yt-dlp home; the HLS fix candidate (`593b3ad77f50e2af64589d84a005fad5ce79495e4280011f3e240a6961ba9730`) remains unapplied. `_recover()` changes an `output_ready` task to a waiting state and the worker can process it. The normal publish callback also invokes fragment and queue cleanup; the SSH publisher deletes the local source after publishing. These behaviors are incompatible with this recovery's preservation and startup-safety requirements.
- No available in-process route coordinates task memory, `.tasks.json`, and the MP4 journal for this one record; an external file write could race or be overwritten by the running app. This environment has no CT108/PVE/NAS connection, so current task/queue/MP4/NAS/backup/lock state was not rechecked. No NAS or local-file operation was performed, and no recovery tool was prepared because it could not safely finalize without violating these invariants.
- Evidence: `/tmp/dldws001-gana-recovery-preflight-20261023-codex/result.md`, SHA-256 `0b1ed3f8db9179f233a098e6a56c79622304ac1782bafa9987fa021a86f623c7`. Minimum next step: separately authorize a narrowly scoped in-process or explicitly quiesced completion path that coordinates queue/task locks and durable state, blocks replay during the transition, registers NAS with verified no-clobber semantics, and preserves the local MP4/TS/fragments; separately authorize any image/service change needed to make that path available. Fresh read-only CT108/NAS/backup evidence is also required before external writes.

## USER-APPROVED EXECUTION CHECKPOINT — DLDWS-001 downloader-only HLS fix and controlled service rollout (2026-10-23)

> TASK_ID: DLDWS-001; STATUS: IN_PROGRESS; CONTRACT_VERSION: 1.0.0; REQUIRES_WORKSTREAMS: downloader,discovery-writer-safety. This checkpoint supersedes prior read-only/NOT_DEPLOY restrictions **only for this exact authorized scope**; all unrelated contract protections remain active.

- **EXPLICIT USER AUTHORIZATION (2026-10-23)**: Implement and verify the minimal HLS MP4 completion fix; prevent automatic replay of any prior failed task/journal (especially GANA-3223 failed-task + sealed `output_ready` contradiction) on startup; prepare trustworthy backups of current state/config and a rollback plan; if the complete live preflight passes, build and deploy **only** the Downloader `missav-dlp-web` service/container using the exact verified runtime manifest; check real operation with **one** authorized new download through HLS→globally serialized MP4 remux→no-clobber NAS publication→durable complete task state. User-approved download concurrency remains `max_concurrent=4`; MP4 remux one job globally at a time, independent of download concurrency. This is actual conditional build/release/restart and a one-job canary authorization, not just another read-only study.
- **SCOPE**: Downloader HLS output-result collection must no longer look for `.<task_id>.ytdlp-home`; HLS must accept the single validated main MP4 and yt-dlp keeps its sidecar/home rules. Reuse frozen isolated HLS candidate `/tmp/dldws001-gana3223-hls-result-fix-20261022/teddy_mp4_queue.py` with SHA-256 `593b3ad77f50e2af64589d84a005fad5ce79495e4280011f3e240a6961ba9730` (13-group offline smoke PASS), after verifying its provenance, compatibility and narrow diff against **actual deployed** `/app` overlay, not incorrectly replacing it with historical canonical raw code. Add minimal generic startup recovery hold: a failed/error/cancelled/completed task with a sealed journal is never implicitly returned to eligible queue/published/retried/cleaned on restart; retain journal/MP4/segments/task and require a separately controlled reconciliation. Hold must engage **before** any startup worker can pick a job and must survive the full release/restart. Do not hardcode GANA or any other title/UUID into product code.
- **LIVE-ONLY PRECONDITIONS**: Verify from the authorized **Proxmox/CT108 operator context** (do not bypass Docker permissions): actual directory/Git root/branch/remote SHA, operating service/container/image/Compose and mounts, current task set and hash/mtime, sealed journals/queue locks and process activity, all GANA 2,353,735,715-byte MP4/TS/fragments unchanged and SHA matching sealed output, and old four failures unchanged; check disk, remote NAS directory and absence/collision for *any* canary destination, credentials via redacted key existence only, Writer socket liveness and dependency/Compose compatibility. Verify an **independent current backup** of `.tasks.json`, sealed queue metadata, relevant configs, deployment manifest/image ID and a reliable restore path. Preserve source materials without touching/rewriting them. A stale backup or inability to read current Docker/NAS/Writer identity means STOP before any restart/build-activation; do not use dangerous chmod/chown/socket manipulation or a blind Docker stack up. Existing user-provided read-only live observations are positive evidence, but Codex without CT108 access cannot claim live preflight or execute deployment.
- **SAFETY BEFORE DEPLOY**: Test recovery hold against sealed `output_ready`+failed status, all other terminal statuses and normal new jobs; verify zero old jobs auto-convert/auto-publish/auto-delete and no unintended side effects on Writer; test HLS and yt-dlp behavior narrowly. Back up current runtime code/container/Compose and authoritative state, attest candidate image and only changed module(s), preserve original image for rollback. Prove a safe quiesced, single-Downloader-service replacement route with the exact verified mounts/env/flags (no Gluetun/Writer/Selkies/Stage11 management); ensure restored state cannot accidentally replay on rollback; observe start-up first, before triggering any canary. An uncertain lock/queue/Writer/socket or ambiguous rollback must BLOCK deployment.
- **LIVE CANARY**: Only after startup safety and healthy Downloader are verified, initiate exactly one user-authorized **new** download (user-initiated source URL or pre-agreed harmless test asset); verify local download, one global ffmpeg remux, actual HLS output collection, SSH NAS no-clobber atomic finalization and remote bytes/checksum as supported, durable `완료` task state, and that none of the previous five task records/media/queue artifacts changed. Check true operational NAS code, not stale repo assumptions. NAS writes authorized only for this one new canary and distinct GANA under the separate one-job approval when its isolated safe recovery gates later pass. No speculative mass retries.
- **PROHIBITED**: Never modify/delete/reset/requeue/auto-run the four old failed tasks or GANA, GANA local MP4, old MP4/TS/fragments or old queue records. Never overwrite existing NAS or other completed files, reuse an occupied destination or bypass locks. No blanket cleanup, filesystem restructuring, unrelated services, Stage11 subtitle changes, Discovery DB/Writer socket modifications, secrets exposure, or changes to contract designs. The older separate conditional approval to publish **only GANA** remains valid, but this rollout **does not authorize its replay, cleanup, conversion or unsafe one-off recovery**. Any extra source/local-media cleanup needed solely for the **new** successful canary may follow existing verified normal policy after final NAS proof; no old-job cleanup.
- **IMPLEMENTATION ROUTE**: Isolated verified worktree and reviewable minimal diff; fail-closed if canonical repository source differs from final runtime overlay, required frozen candidate absent/changed, or live dependencies/Compose cannot be established. Preflight/report first; successful bounded tests permit scoped commit/build/deploy under this user approval only after all necessary gates PASS. Record exact image, backup and restoration IDs, pre/post task and journal hashes, tested API/health checks, new canary E2E evidence, regression outcomes in both ACTIVE_WORK files and CURRENT_HANDOFF. Existing technical smoke PASS does not itself prove product PASS.
- **ACCEPTANCE**: `LIVE_PREFLIGHT`, `BACKUP_ROLLBACK`, `HLS_RESULT_FIX`, `OLD_FAILED_REPLAY_HOLD`, `WRITER_COMPATIBILITY`, `IMAGE_BUILD`, `DOWNLOADER_ONLY_DEPLOY`, `FOUR_OLD_JOBS_PRESERVED`, `GANA_ORIGINAL_PRESERVED`, `NEW_JOB_DOWNLOAD`, `GLOBAL_MP4_SERIAL`, `NEW_JOB_NAS_NOCLOBBER`, `NEW_JOB_COMPLETE_DURABLE`, `NORMAL_NEW_DOWNLOAD_PIPELINE`, `GANA_NAS_PUBLISHED`. Each PASS/FAIL/INCOMPLETE/NOT_RUN individually with evidence. If no live CT108 access is available, report `DEPLOY=BLOCKED_NO_LIVE_ACCESS` with precise minimal operator commands; do NOT claim it shipped. If any precondition fails, STOP without deploy/restart/partial production edits.
- **NEXT DECISION**: Once new-product canary is PASS, separately plan the already conditionally authorized preservation-safe GANA-3223 NAS completion without local original deletion; do not let it block new-job normal operation or expand this approval to other four failed tasks.



## COORDINATION RESULT — DLDWS-001 urgent Downloader pipeline normalization (2026-10-23)

> TASK_ID: DLDWS-001; STATUS: IN_PROGRESS; CONTRACT_VERSION: 1.0.0; REQUIRES_WORKSTREAMS: downloader,discovery-writer-safety.

- Shared-work tracking only; no Writer code, socket, service, or state was changed. The approved isolated HLS fix has 13/13 prior HLS/yt-dlp groups PASS and the generic failed/ambiguous MP4 startup hold has a separate 23/23 synthetic PASS. These results do not establish live Writer compatibility or release readiness.
- Live CT108/PVE/NAS configuration and Writer socket liveness could not be checked. Docker image inspection was denied by the local Docker socket permissions. `BACKUP=INCOMPLETE`; `BUILD=NOT_RUN`; `DEPLOY=BLOCKED`; `NEW_DOWNLOAD_E2E=NOT_RUN`. No production write or service action was performed; current GANA and four historical job bytes are UNKNOWN because they were not re-read.
- Evidence: `/tmp/dldws001-urgent-pipeline-20261023-codex/result.md`, SHA-256 `705002bf27e1453d24e2300188bec237759b9cde48bce983f5668465ed0c57c6`. Writer socket safety remains UNRESOLVED.
- NEXT: request fresh redacted read-only CT108 evidence for Writer socket and deployment dependencies before any release re-evaluation.

## COORDINATION RESULT — DLDWS-001 SSH NAS no-clobber isolated candidate (2026-10-23)

> TASK_ID: DLDWS-001; STATUS: IN_PROGRESS; CONTRACT_VERSION: 1.0.0; REQUIRES_WORKSTREAMS: downloader,discovery-writer-safety.

- This is a result record under the existing conditional Downloader release approval, not permission to publish product code, build/deploy an image, change a container, write to NAS, or process any prior job. The Discovery Writer Safety workstream participated in shared tracking only; no Writer code, service, socket, or data was changed.
- The hash-pinned source snapshot `/tmp/dldws001-mp4-startup-safety-20261022/teddy_storage.py` matched the user-provided SHA-256 `85194b4acec92619601888fe6d611c26cfdfd63f716b3e66baeb6ff2673a1bd1`. In those exact bytes, `_ssh_publish_completed_file()` contains no executable `mv -f`; the text appears only in a comment. The actual gaps were that a same-hash existing final path was accepted as success and caused local source deletion, and `ln` lacked exact-target (`-T`) semantics for a directory appearing at the final name after the existence check.
- Downloader-only isolated candidate: `/tmp/dldws001-nas-noclobber-20261023/teddy_storage.py`, SHA-256 `d678abce28a0545d7e9d47633f79cff729c18d7e9436b82c2c31c2921fe914f9`. Only this runtime file was changed. Any existing final path is now a collision; partial-path symlink/special-file checks happen before transfer; final publication uses `ln -T --` for atomic exact-name hard-link creation; local source removal remains after remote final size and SHA-256 verification. Existing HLS/startup files stayed unchanged: `app.py` `f2ffdc1542f1203e7c533bf0116d617bb9f7d2a9d9fb937455b75f17d640244e`; `teddy_mp4_queue.py` `cb583308c4b3a73b4580fb29dd4d0c63899e3d07fa33561bfc9843fb1ddc7649`; `teddy_download_safety.py` `8588cf34936aba6936ab943aaa845919a51e8bd68b58e0c2e5ef87e6eecb830d`.
- Targeted local synthetic test: Python 3.10.22; 11 tests passed, 0 failed/errors. It exercised real local shell `ln -T`, normal publish, same/different-hash final collisions, pre-existing file/directory/symlink, final-name file/directory/symlink races, temp size/SHA mismatch, final SHA mismatch, interrupted transfer, and local source preservation. SSH/rsync transport was simulated against temporary local directories; no NAS or external network write occurred. Test SHA-256 `c2887a11bc91953e3961b88fbbc07dc5901ef6facca6f46e600722ea87388ee8`; result JSON SHA-256 `c01e8f5a772143598140e22dc2950539e60caa898c09c4359beadccf82ec961c` at `/tmp/dldws001-nas-noclobber-20261023/evidence/result.json`.
- `NAS_NO_CLOBBER_CANDIDATE=PASS` for isolated behavior; actual CT108 source/runtime and the NAS implementation's `ln -T` support were not re-read. User-reported build image `sha256:85d4968deef79c1720951d1a5dd8558a17f9318d838762cbe0e5256921d5ad0b`, old running image `sha256:7200290e8af11d9f253a5efd028bf3be2a2757af9049f0bb9e43bd04f821f2d8`, and backup PASS remain user-provided facts, not independently verified here. `IMAGE_BUILD=NOT_RUN`; `PRODUCTION_DEPLOYMENT=NOT_RUN`; `NAS_WRITE=NOT_RUN`; no GANA or prior failed job was transferred/retried/deleted.
- Next gate: on CT108, read-only verify `/app/teddy_storage.py` still hashes to the reviewed source, verify the deployed/base image identity and that the new base contains the three frozen approved files, and query the NAS's `ln --help` through the configured SSH identity to confirm `-T`/`--no-target-directory`. If any check fails, do not build/use this candidate. Only then prepare a uniquely tagged one-file overlay based on the existing image, without changing that image or the running container; subsequent operational activation remains subject to all existing preflight gates and the conditional deployment scope.
## COORDINATION — DLDWS-001 SSH NAS no-clobber final verification (2026-10-23)

> TASK_ID: DLDWS-001; STATUS: IN_PROGRESS; CONTRACT_VERSION: 1.0.0; REQUIRES_WORKSTREAMS: downloader,discovery-writer-safety.

- This Downloader-only final 14-test run supersedes the earlier 11-test result in this checkpoint; it adds special-file and task-transition integration cases. The isolated runtime candidate stayed at SHA-256 `d678abce28a0545d7e9d47633f79cff729c18d7e9436b82c2c31c2921fe914f9`.
- Python 3.10.22: `TESTS_RUN=14`, PASS=14, FAIL=0, ERROR=0. In addition to transfer/collision/hash/race coverage, the actual `_publish_pending_task_ssh()` path marked a synthetic new task complete only after verified publication; its collision failure followed `mark_publish_error()` and retained `local_result_path(s)` and local bytes.
- Final test copy SHA-256 `e4bfde0d8e2ea45e85d102e55134df8fc5330a0bf7a3559bf43b7d7b9d20f605`; result JSON `/tmp/dldws001-nas-noclobber-20261023/evidence/result.json` SHA-256 `d77adcabe83625b5c1ea24c2661304ba2310d5fa7344bd445b62bc6167a7136f`.
- A preserved historical smoke copy expects a same-hash pre-existing final to count as success and delete the local source. That assertion now conflicts with the explicit collision policy and was not modified or rerun; update a new test copy before using that historical suite. This does not change the 14 focused-test result.
- Actual CT108 runtime bytes and NAS `ln -T` support are still unverified. No NAS write, image build, production deployment, retry, or production file change occurred. The next gate remains a CT108 read-only source/image check and SSH `ln --help` capability check before preparing a unique one-file overlay.
