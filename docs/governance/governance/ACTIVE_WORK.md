# Governance workstream — active work

WORKSTREAM: governance
TASK_ID: NONE
STATUS: INACTIVE
CONTRACT_VERSION: 1.0.1
REQUIRES_WORKSTREAMS: governance

## DLDLIB-001 CLOSEOUT — 2026-10-28 KST

DLDLIB_CLOSEOUT=PASS: user approved closure after the production evidence recorded below: SIGINT shutdown exit 0, existing candidate image deployment, MAX_TITLES=500, authenticated library HTTP 200 and user-confirmed 252 titles displayed in the web UI. The independent API summary/items counts were not read; no broader product-quality completion is implied. The exact deployment and previous blocked-attempt evidence remain below and in canonical history.

ROUTING_RESTORED: Governance INACTIVE / NONE (requires governance); Downloader and Discovery Writer Safety IN_PROGRESS / DLDWS-001 (requires downloader,discovery-writer-safety). Stage9 remains IN_PROGRESS / STG9MEDIA-001 and Stage11 remains IN_PROGRESS / S11-WX011. The original DLDWS-001 purpose, status, approvals, candidates, evidence and backup preservation policy are retained. Earlier DLDLIB-001 scopes, approvals and next decisions below are historical and grant no continuing operation authority. This closeout only edits routing, active-work and handoff documents; it authorizes no code, Docker, NAS/DB/Jellyfin, Stage9, Writer, Stage11 or backup operation.

### ACCEPTANCE_CRITERIA

Restore and structurally validate all routes, pass DLDWS-001 paired and unchanged Stage9/Stage11 preflights and governance smoke, pass git diff --check, normal fast-forward and exact remote readback. Preserve all historical evidence. Original route details are independently anchored at pre-transition commit a7f90446094f6a703d88e5ebb3d3517a8a4ba2f7 and prior document blob IDs below.

### NEXT_DECISION

Governance is inactive; proceed with DLDWS-001 only within its original authorized scope. Any new scope or deployment requires its own authorization. No product/runtime activity is authorized by DLDLIB-001 closeout.


## HISTORICAL CLOSED DLDLIB-001 OPERATIONS — 2026-10-28 KST

The user explicitly authorized the bounded Downloader-only production image deployment below. This supersedes the earlier DLDLIB-001 coding-phase prohibition on image build/container replacement/restart only for this exact operation, conditional on every safety gate. Prior coding evidence, DLDWS-001 and backup policies are preserved. Governance coordinates authorization/evidence, Downloader owns the change, and Writer Safety participates only to verify Writer invariance and compatibility.

### APPROVED_SCOPE

- After this approval is validated, committed, fast-forwarded and read back from canonical, read-only recheck actual CT108 host/container identity, image, complete Compose project/service/image/network/environment/mount/privilege/command configuration (never expose secrets), current file SHA and byte equality with the canonical pre-fix file, old-image/config rollback, live downloads/remux/tasks and MP4 journals, startup replay of old failures/GANA, Discovery DB read-only accessibility, Writer socket and shared-lock compatibility, and independent Stage9 scheduling.
- Only when all gates including startup and rollback safety PASS: build a reproducible uniquely tagged single-file image layer based on the verified running image ID, replacing only /app/teddy_library_api.py with the canonical MAX_TITLES=500 version. No docker commit or full-source rebuild. Verify candidate import/constant and unchanged runtime configuration. Preserve the old image and Compose configuration; replace only the actual Downloader Compose service without dependency recreation and preserve command, networks, mounts, secrets, environment and permissions.
- Verify running container, constant 500, authenticated /api/library HTTP 200 with actual count, list count and default ordering, web File Management library display, and unchanged jobs/queue/journal, Writer and Stage9 status. Any rollback requires a safe startup/replay path and preserved current state; stop if unproven. Record outcomes and precise evidence in ACTIVE_WORK and canonical handoff. User-supplied baseline image sha256:9ceedeba292ae50980e6fb143589b7c0e12d1abf8c34d82fa49de8a5a500402f and file SHA-256 7847786d04ac9af4c533f4163633db837954b5d15f9723b53fe68c50f72ed055 are historical until freshly verified.

### PROHIBITED_SCOPE

No product source change beyond already published constant, unrelated service/container recreation, direct patching of running container, Docker commit, forced job/download/Organizer/Stage9 work, Writer socket/service modification, Stage9 timer/service changes, NAS/Jellyfin/Discovery DB/settings writes, task or queue edits/deletion, backup movement/deletion, Stage11 changes or broad refactoring. No build/deploy if any mandatory safety gate is unknown or fails; no unsafe rollback or startup replay workaround. Do not publish secrets.

### ACCEPTANCE_CRITERIA

Approval readback, all governance checks and clean diff PASS before operations; fresh baseline, restart replay and rollback safety PASS before image creation/deployment. Candidate contains only the approved file difference and reads MAX_TITLES=500; real API and authenticated web UI verification are separate outcomes. If UI is unverified, do not claim full completion. Preserve unrelated services/data. Report each gate independently, image IDs and canonical SHA.

### DLDLIB-001 SIGINT DEPLOYMENT — 2026-10-28 KST

- User requested reuse of candidate sha256:dd5d4e96f0292ff931edd8a239387d8de735243d13d942032ac8c8afacce2c77 and reported SIGINT handled, SIGTERM not handled, prior SIGKILL exactly 30 seconds after SIGTERM, and no PVE kernel OOM log. Those signal/OOM findings are user-supplied. Canonical base was a2a56ae58ab7a756b78643e1460989191cdeaf3d. All three DLDLIB-001 routes stayed IN_PROGRESS; Stage9 and Stage11 routes unchanged.
- User explicitly confirmed a maintenance window with no new download/retry and reconfirmed no running/waiting tasks. Pre-stop: original container ffc4bef1e013c4e784b96bc219f19f6c5491d22937ad138c378dc0c559d7c3b2, old image sha256:9ceedeba292ae50980e6fb143589b7c0e12d1abf8c34d82fa49de8a5a500402f, original library SHA-256 7847786d04ac9af4c533f4163633db837954b5d15f9723b53fe68c50f72ed055; task records 5 complete; JSON queue 0. Backed-up eight Compose files matched original bytes/order; saved environment, old-image identity and candidate override rendered with only image difference.
- docker stop --signal=SIGINT --timeout=30 exited promptly with container exit code 0, OOMKilled=false; no SIGKILL indicated. Post-stop five completed tasks, JSON queue 0 and no legacy .part.ts; tasks SHA-256 27f8d654589a43d9664a132b177fee46f6ac1a88740ef5c8a80c900cb2a447c1 and settings SHA-256 6c11ebcb949b0ad0c65a74af503bb421b2ee41979d72cde53e84c63b0fe115ee matched pre-stop. No large media content was read.
- DEPLOY=PASS: reused existing candidate and changed only Compose service missav-dlp-web with --no-deps --no-build --pull never. New running container f73ccdb2431f916163f99e289288e5c21b3f3572706f85151626bd4902430527 uses the candidate image; python -B import MAX_TITLES=500 and file SHA-256 fd615dafaa3ae91f39daa4653d7f8ebe55a154be032191bcb4390a75451708ee PASS. Post-deployment 25 runtime configuration comparisons passed, including env, image, command, network, ports, mounts, group, user, privileges and restart policy.
- LIBRARY_API=PASS for HTTP: production server logged authenticated user-session GET /api/library?sort=nas_added&order=desc HTTP 200. WEB_UI=PASS from user observation: File Management > held library displayed 252 titles. The separate API summary.total_titles/items counts were not independently read, and no broad product-quality claim follows from the UI observation.
- Post-start task/settings hashes unchanged, five tasks completed, JSON queue zero and four legacy MP4 files present. Writer socket connection passed; Writer and both Stage9 timers active. Old rollback image remains locally available; root-only saved Compose inputs/environment and original-image rollback procedure remain available; rollback was NOT_RUN. No new image build, forced download/recovery, deliberate NAS/DB/settings mutation, other container restart, Writer/Stage9 or Stage11 change occurred. The ordinary library request used its existing read-only NAS inventory path.
- DLDLIB-001 remains IN_PROGRESS across Governance, Downloader and Discovery Writer Safety. Preserve prior DLDWS-001 history and backup policy. User may end maintenance; any restoration of original routes requires a separate closeout step. Continue monitoring within existing task scope.

### DLDLIB-001 DEPLOYMENT RESUMPTION — STOPPED AT SHUTDOWN (2026-10-28 KST)

- User submitted authenticated /api/tasks HTTP 200 with 5 complete and no running/waiting work, zero MP4 JSON journals, and eight original Compose files backed up with matching effective configuration. During the single-user maintenance window the user reconfirmed five completed tasks and committed to submit no new download/retry until notified.
- Read-only checks confirmed container ffc4bef1e013c4e784b96bc219f19f6c5491d22937ad138c378dc0c559d7c3b2, old image sha256:9ceedeba292ae50980e6fb143589b7c0e12d1abf8c34d82fa49de8a5a500402f and library SHA-256 7847786d04ac9af4c533f4163633db837954b5d15f9723b53fe68c50f72ed055. All eight original/backup files matched; stored order and original image ID matched live container. Compose interpolation values were saved exclusively root-only mode 0600 at /opt/missav-dlp-web/backups/dldlib001-compose-inputs-20261028/compose-interpolation.env; original and backup renders matched and 28 compared runtime configuration properties passed. Root-only candidate override changes the image reference only; original rollback command dry-run targeted only the Downloader service.
- The candidate was built from the verified local old-image tag after confirming its ID. The first BuildKit attempt using FROM sha256:... failed to resolve the local image; a local-tag build succeeded. Candidate sha256:dd5d4e96f0292ff931edd8a239387d8de735243d13d942032ac8c8afacce2c77, tag missav-dlp-web:dldlib001-20261028-v1: old image layer prefix unchanged plus one layer; image config identical; isolated no-network read-only import MAX_TITLES=500 and library file SHA-256 fd615dafaa3ae91f39daa4653d7f8ebe55a154be032191bcb4390a75451708ee PASS.
- During the user-confirmed maintenance window, before shutdown the disk tasks file had five completed, SHA-256 27f8d654589a43d9664a132b177fee46f6ac1a88740ef5c8a80c900cb2a447c1; queue JSON count zero; no active child processes. Docker stop with 30-second timeout returned exit 137 and OOMKilled=true; normal shutdown was NOT established, cause/timing of the OOM flag is unknown. After stop, tasks hash/status, zero JSON jobs, settings SHA-256 6c11ebcb949b0ad0c65a74af503bb421b2ee41979d72cde53e84c63b0fe115ee and absence of .*.part.ts were verified. Large legacy MP4 files were not read or deleted.
- Because the required normal shutdown condition failed, candidate deployment was not performed. The same original container was restarted with docker start after the preserved post-stop state was checked: same container ID and old image, running, Flask startup logged; library file remains old SHA; tasks/settings hashes unchanged, five complete, zero queue JSON; Writer service and Stage9 timers active. The old library 503 fix remains unapplied; authenticated library and UI validation NOT_RUN. No new image was attached to production. STARTUP_REPLAY_SAFETY=BLOCKED and ROLLBACK_READY=BLOCKED for a future rollout until the abnormal stop is understood and a normal safe stop/restart can be established; CANDIDATE_IMAGE=PASS; DEPLOY=BLOCKED; LIBRARY_API=NOT_RUN; WEB_UI=NOT_RUN.
- No NAS/Jellyfin/Discovery DB write, task/queue manipulation, backup deletion, Writer/Stage9 change, forced download/recovery or Stage11 change was performed. DLDLIB-001 remains IN_PROGRESS across Governance, Downloader and Writer Safety; original DLDWS-001 approvals and backup policy are retained. The maintenance window can end because the original service was restarted. Next: investigate exit 137/OOM safely without disturbing service, establish normal shutdown evidence, then recheck all time-sensitive gates before any further deployment.

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


## HISTORICAL CLOSED TEMPORARY TASK — DLDLIB-001 (2026-10-28)

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


## JOINT DEPLOYMENT CLOSED — STG9MEDIA-001 (2026-10-28)

The user explicitly approved this closeout after submitting the missing representative operational evidence. The temporary four-workstream deployment overlay is CLOSED. The original independent routes are restored: Governance INACTIVE / NONE; Downloader and Discovery Writer Safety IN_PROGRESS / DLDWS-001 with their paired requirement; Stage9 IN_PROGRESS / STG9MEDIA-001 with stage9-media only. Stage11 is unchanged.

### APPROVED_SCOPE

Record the supplied evidence, close the temporary joint deployment, restore routing/required-workstream metadata, and update the canonical handoff. Preserve the original DLDWS-001 objective, approvals, deployment/recovery evidence, candidates and backup preservation policy. No backup-policy amendment or backup-cleanup task is registered in this closeout.

### PROHIBITED_SCOPE

No product source, runtime/service/timer configuration or restart, NAS/DB/Jellyfin write, forced download/metadata execution, backup transfer/deletion, Stage11 or Writer implementation change is authorized by this closeout.

### ACCEPTANCE_CRITERIA

The representative scheduled processing and actual NAS NFO/poster plus Jellyfin visibility evidence are recorded with correct attribution; original route/task/requirement sets are consistent; governance checks and diff check pass; the canonical branch is updated by normal fast-forward and read back exactly. Stage9 automatic operation and remaining independent work are preserved without a whole-product completion claim.

### EVIDENCE — USER-SUBMITTED CT108 MEASUREMENTS (2026-10-28 KST)

- The user submitted the operational measurements below; Codex did not execute the deployment, NAS checks, DB updates, or Jellyfin operations represented by them.
- PPPE-446: scheduled Stage9 processing COMPLETED; nfo_status=COMPLETE and poster_status=COMPLETE; NAS MP4 size comparison PASS; actual NAS NFO exists (769 bytes); actual poster.webp exists (11,010 bytes). jellyfin_notification_status=VISIBLE, jellyfin_recovery_status=VISIBLE, and media_jellyfin_visibility.status=VISIBLE; visible_at=2026-10-28T00:02:20+00:00; last_error=NULL and no media error.
- SNOS-403 and FNS-258: NFO/poster completion and Jellyfin VISIBLE confirmed by the user. Previously submitted operational logs confirm the dedicated timer is active, the generic Completion Runner uses --skip-media, and recent scheduled invocations completed with one media item and zero failures.
- Read-only canonical code review: teddy_discovery_media_filestation.py:_publish_one validates exact paths and input hashes, accepts an identical existing sidecar without rewriting it, rejects conflicting content/type, rechecks before create-only upload, handles concurrent creation as an error, and verifies final owner, size and SHA-256. _upload_create_only does not request overwrite and sets create_parents=false; publish_bundle restricts canonical sidecar filenames and only reads the video. This is a source review, not a new production permission or no-overwrite test.
- These measurements satisfy the bounded scheduled-run DB/NFO/poster/Jellyfin closeout evidence for the joint deployment. They do not establish whole-product completion, all-title quality, or resolution of every pending/retry/poster item.

Validation at closeout: all-workstream structure, restored DLDWS-001 paired preflight, independent STG9MEDIA-001 preflight, unchanged S11-WX011 preflight, governance smoke 21/21 and git diff --check PASS.

### NEXT_DECISION

Joint deployment coordination is closed. Continue the existing Stage9 automatic operation and independently registered Stage9 work within its existing approval boundaries; unresolved items are not declared complete. DLDWS-001 resumes its original paired routing and preserved approval/history; Governance is inactive. Any new feature, cleanup or operational mutation requires its own matching task authorization. All earlier joint deployment instructions below are retained as historical records and grant no renewed deployment authority.


## HISTORICAL CLOSED JOINT STAGE9 OPERATIONS AUTHORIZATION — 2026-10-27

Teddy explicitly approved local CT108 **root** execution for the dedicated Stage9 service on 2026-10-27, superseding only the previous *local non-root* service requirement. Stage9 NAS access MUST use existing non-admin `stage9_media` over verified HTTPS File Station, never administrator SSH. Prior joint operations records remain CLOSED historical evidence.

### APPROVED_SCOPE

- Temporarily route Governance, Downloader, Discovery Writer Safety, and Stage9 together as `STG9MEDIA-001`, preserving all DLDWS-001 and Stage11 work.
- Deploy the already-promoted immutable File Station Stage9 runtime, update only the generic wrapper to use existing `--skip-media`, retain the generic 60-second schedule/downloads/Organizer/metadata recovery, and install a separate Stage9 hourly randomized timer/service with max one item per run and Stage9-only failure-stop.
- Before production writes, confirm CT108 provenance and current service state, private credentials/CA, database integrity and backup, shared locks, NAS create-only sidecar rights, and a single-owner Stage9 scheduling path. Verify only one natural scheduled representative run and its DB/NFO/poster/Jellyfin effects; report no-work separately from actual publication.
- Local root preserves current root-only DB/WAL, Discovery read access, and shared title-lock semantics, without broad local ACL or ownership changes. NAS publisher remains least-privileged, with pinned TLS and existing no-overwrite protections.

### PROHIBITED_SCOPE

- No broad ACL laboratory or recursive chmod/chown, NAS administrator SSH publisher, TLS bypass, existing MP4/NFO/poster overwrite/delete, retry resets, bulk processing, new Stage9 code implementation, Writer socket changes, Stage11 work, or unrelated Downloader behavior changes. Stop if File Station Download 502 or actual JAV create-only permission remains unresolved.
- No full Downloader code refactoring until Stage9 is complete. After Stage9 and the separately planned four MP4 recovery items, review the full Downloader source read-only, report duplicates/structural issues, and obtain separate refactoring approval.

### EVIDENCE AND NEXT_DECISION

- Latest verified remote branch before registration: `3f159e175e4b2c915158b900e8e96a0ef9ddd792`; Stage9 skip-media smoke was previously repaired. CT108 generic timer `inactive/enabled` and old wrapper SHA `e49be466924287f328ea4d482b6a4806f0142cb4b8a71268c25bdb2365552b39` with no `--skip-media`; dedicated timer absent. Root-only directories and DB confirmed. Debian `acl` package installed, no permissions changed. All production Stage9 deployment and NAS/Jellyfin writes remain NOT_RUN.
- Proceed with narrow read-only live preflight. On completion or blocker, restore original routes (Governance `INACTIVE/NONE`, Downloader and Writer `DLDWS-001` with paired requirements, Stage9 `STG9MEDIA-001` alone), preserving Stage11.

## OBJECTIVE

Record the user's approved personal-use, right-sized development and validation priority in the canonical common contract and AGENTS.md; close GOV-008 after exact readback.

## APPROVED_SCOPE

- Edit only AGENTS.md and common contract, with minimum routing/active-work metadata needed for GOV-008 activation, version alignment, and closure.
- Prioritize practical personal use; retain existing files' no-delete/no-overwrite safeguards, scoped paths, and fail-closed behavior; avoid disproportionate validation tooling.

## PROHIBITED_SCOPE

- No product, Stage9, Stage11, Downloader, Writer Safety, NAS, DB, Jellyfin, account, timer, or service changes.
- No weakening existing data protection or authorization rules; no claimed runtime validation.

## ACCEPTANCE_CRITERIA

- Approved principle appears in both AGENTS.md and the common contract with consistent version and routing metadata.
- Existing independent workstream states and contracts remain unchanged.
- Canonical branch fast-forward and exact readback, then Governance restored to INACTIVE / NONE.

## EVIDENCE

- GOV-008 CLOSED after exact remote readback; common project contract updated to v1.0.1 and AGENTS.md updated with personal-use development priorities, minimal validation, and retained essential no-overwrite/fail-closed safeguards.
- Policy commit: 61d38019e746b4c0e079b302f9a9089ac21e7faa. Canonical branch: teddy-subtitle-stage11.
- Validation: four updated policy/metadata files exactly read back; existing Stage9, Stage11, Downloader and Writer Safety task routes unchanged; no runtime/product/NAS/DB/service changes.
- User explicitly approved GOV-008 in chat on 2026-10-27 KST.
- Activation base 77b3c388c2e31d311321883001c86200d3482e6d on teddy-subtitle-stage11.
- Product and runtime modifications are outside this approval.

## NEXT_DECISION

GOV-008 is CLOSED; Governance is INACTIVE / NONE. Stage9 remains a separate approved task; any future governance policy change needs its own approval.

## PREVIOUS GOVERNANCE RECORD (PRESERVED)

## OBJECTIVE

Close the temporary joint Stage9 integrated transition at the NAS least-privilege access gate, record the verified reason, and restore the original workstream routing. No operational changes were made.

## APPROVED_SCOPE

- Restore Governance to `INACTIVE / NONE`, Downloader and Discovery Writer Safety to `IN_PROGRESS / DLDWS-001` with their original required-workstream pair, and Stage9 to `IN_PROGRESS / STG9MEDIA-001` with its original single-workstream requirement.
- Preserve the joint activation and the Stage9/DLDWS evidence, record the NAS access blocker, and verify restored routes and protected Stage11 status.

## PROHIBITED_SCOPE

- No further operational or product changes are authorized by this closed Governance activation.
- No NAS account, ACL, credential, file, CT108 account, wrapper, service, timer, release, database, Jellyfin state, Downloader behavior, Writer socket, or Stage11 data was changed.
- No contract, validator, or shared project policy was changed.

## ACCEPTANCE_CRITERIA

- The one-time joint registration is recorded and its exact canonical activation readback is verified.
- All original routes are restored and the Stage11 `S11-WX011` route remains unchanged.
- The unresolved NAS authentication/least-privilege prerequisite is accurately recorded; no operational mutation is claimed.

## EVIDENCE

- User approved this integrated transition on 2026-10-26 KST. Activation base and freshly read remote `teddy-subtitle-stage11` SHA: `9c89efe29c5b9af7b5cc70aff305738a9723d2c2`.
- Existing promotion `43fa8c034d4c6198507a2e7138829b6f3f6cfc15`, Stage9 offline verification, and prior operational observations are evidence only; no prior blocked step is treated as passed/current without revalidation.
- Activation commit `ac61cd8df99f98aa7f678f4684b08836d9177e9e` was posted as a fast-forward and all five documents were exactly read back before live inspection.
- Read-only CT108 check confirmed host `downloader`, `uid=0(root)`, PID 1 `systemd`; generic timer `inactive/enabled`, 60-second schedule, static service `inactive`, root execution, wrapper SHA-256 `e49be466924287f328ea4d482b6a4806f0142cb4b8a71268c25bdb2365552b39`, and no `--skip-media`.
- DSM was `7.2.2-72806 Update 4`; official DSM terminal policy limits SSH/Telnet login to local administrators. Existing SSH identity is `ssikgun` in `administrators`, and the exact Stage9 library root is mode `777`; its current ACL contains only existing principals and no Stage9 publisher. `GANA-3223` directory was absent.
- Unauthenticated DSM API Info GET over HTTP reported File Station Info v2, Upload v3, CheckPermission v3, MD5 v2, and CopyMove v3. HTTPS port 5001 failed system trust with an untrusted issuer. Existing SSH identity has no noninteractive sudo; therefore no trusted authenticated DSM provisioning/API route for a new non-admin File Station principal was available. Do not send DSM credentials over HTTP or reuse the administrator key in the runtime.
- The least-privilege publisher gate failed. No NAS account/ACL/credential, CT108 account/permission, product source, runner/wrapper, systemd unit/timer, release, DB/backup, NAS file, or Jellyfin state was changed. DLDWS-001 and S11-WX011 were not modified.
- Restored route validation and exact remote readback are recorded at this closure; operational access and deployment remain blocked.

## NEXT_DECISION

Governance is inactive. The Stage9 integrated transition cannot resume until a supported authenticated DSM provisioning path and trusted TLS authority are available for a non-admin, path-limited File Station publisher. No operational authority remains from this closed joint registration.

## HISTORICAL CLOSED GOVERNANCE RECORDS

All pre-existing closure and GOV-007 evidence below remains historical and unaltered; it does not override this current task while this joint registration is active.

- ## CLOSED JOINT OPERATIONS AUTHORIZATION — STG9MEDIA-001 (2026-10-26)

The user explicitly re-authorized the unfinished integrated Stage9 cutover on 2026-10-26 after direct Codex execution-environment verification established access to CT108. This reopens only the exact joint task below; the previous closure remains preserved in the parent commit and is not treated as continuing authority by itself.

### APPROVED_SCOPE
- Create a dedicated non-login, non-root Stage9 system account and grant only the verified minimum DB, lock, SSH credential, Jellyfin credential, and runtime access required by the promoted Stage9 runner.
- Use the already promoted canonical --skip-media Completion Runner path to preserve the existing 60-second Downloader schedule and its existing download, Organizer, and metadata-recovery behavior while removing Stage9 Media work from that path.
- Install an immutable Stage9 release from already promoted source 43fa8c034d4c6198507a2e7138829b6f3f6cfc15; install and activate only the dedicated Stage9 service/timer and its Stage9-only failure stop.
- Create a fresh Stage9 DB backup only if required by the validated transition, verify integrity and an isolated copy, then observe at most one item per scheduled Stage9 invocation. Existing GANA-3223 is not to be reprocessed.
- Verify one normal scheduled run, preserve NFO/poster/video no-overwrite behavior, bounded retry/lock/Jellyfin policies, and the generic Downloader path; restore the original workstream routing at closeout.

### PROHIBITED_SCOPE
- No root execution for the dedicated Stage9 service, broad recursive ownership or mode changes, credentials in logs/Git/environment examples, NAS-wide permission grants, or permission expansion beyond exact verified paths.
- No download or MP4 policy changes, forced Downloader/Organizer runs, Writer socket source/service changes, Stage11 changes, other service/timer changes, product-source reimplementation, or unapproved job/file changes.
- No database initialization, legacy-state/retry reset, automatic backup restore, forced termination of publication, existing NAS artifact replacement, bulk processing, or Jellyfin actions beyond the promoted bounded implementation.
- Stop if minimum privileges, remote SSH publish scope, concurrent-writer safety, live data integrity, or timer separation cannot be proven.

### ACCEPTANCE_CRITERIA
- The four selected routes and active-work files authorize exactly STG9MEDIA-001 with the complete required-workstream set and approved contract versions.
- Dedicated service runs only as the dedicated non-root account, with verified path-limited access; the old generic timer continues its 60-second schedule with --skip-media.
- No two active schedules can process Stage9 Media; the new hourly timer has its bounded limits and failure-stop behavior.
- The first observed scheduled run is recorded separately from a successful artifact lifecycle; no unsafe DB, NAS, Jellyfin, Downloader, Writer, or Stage11 change occurs.
- After success or safe stop, Governance, Downloader, Discovery Writer Safety, Stage9, and Stage11 are left in their authorized final routing states and the remote readback is exact.

### EVIDENCE
- User approval received 2026-10-26 KST. Activation base and current remote SHA: 2cc70990460e79eb2e128a1efdcb1846905ae324.
- The already promoted product change is 43fa8c034d4c6198507a2e7138829b6f3f6cfc15; it will not be reimplemented or re-promoted.
- Previous joint task closure and its evidence remain in canonical history at parent 2cc70990460e79eb2e128a1efdcb1846905ae324.
- Direct authorized CT108 preflight confirmed hostname `downloader`, root operator, PID 1 `systemd`, and the existing Runner SHA-256 `e49be466924287f328ea4d482b6a4806f0142cb4b8a71268c25bdb2365552b39`. The existing generic timer remains inactive/enabled and its wrapper has no `--skip-media`.
- The cutover stopped before operational writes because the existing NAS SSH identity is `ssikgun` with the `administrators` group and verified writable access to `/volume1/video`, `/volume1/video/video2`, and `/volume1/video/video2/JAV`; the approved minimum-permission condition is not met. No restricted publisher credential was available or created.
- SQLite was opened with `mode=ro` and `PRAGMA query_only=ON`: integrity was `ok`; 119 jobs were present (109 COMPLETED, 8 FAILED, 2 PENDING, 0 RUNNING), max attempt count 17161, and 109 visibility rows. No DDL/DML was issued. The main DB size/mtime and WAL mtime remained unchanged; SQLite updated the existing SHM file mtime/ctime during the read connection, so SHM metadata side effect is recorded.
- No service account, ACL, wrapper, service, timer, release, backup, NAS artifact, Jellyfin state, or product source was changed. Activation commit `cff602a261a79f0dce7bc31ed445dd05ded2814f` was read back exactly from the canonical branch before the preflight.

### NEXT_DECISION AT ACTIVATION (SUPERSEDED BY CLOSURE)
- Keep this joint task active until the first scheduled Stage9 run is verified or a safety gate forces a documented stop; then close it and restore the original routing.

- The prior Governance closure record is retained in the parent commit at `2cc70990460e79eb2e128a1efdcb1846905ae324`; historical GOV-007 evidence remains below.

## NEXT_DECISION

Before another operating attempt, provide and explicitly authorize a Stage9 NAS identity whose remote command and write scope are constrained to the metadata publisher and the verified library sidecar paths. Do not reuse the current administrators-group SSH identity for the non-root service.

## HISTORICAL GOV-007 (CLOSED)

The following record is retained from the prior closed GOV-007 task. It is historical evidence only and grants no current authorization.

### GOV-007 OBJECTIVE (CLOSED HISTORY)

GOV-007 completed the approved independent Stage9 Media governance registration and is closed after exact canonical remote readback. No Governance task is currently active.

### GOV-007 APPROVED_SCOPE (CLOSED HISTORY)

- Register the `stage9-media` workstream with its approved v1.0.0 design contract, independent router entry, and `INACTIVE / NONE` active-work record.
- Record `STG9-MEDIA-001` only as a proposed, unapproved identifier; Stage9 implementation remains unauthorized and inactive.
- Route Stage9 Media metadata/NFO/poster/Jellyfin item-state behavior away from the generic Downloader area while preserving Downloader `DLDWS-001`, Discovery Writer Safety `DLDWS-001`, and Stage11 `S11-WX011`.
- Restore Governance to `INACTIVE / NONE` after exact canonical readback of the separate Stage9 registration commit.

### GOV-007 PROHIBITED_SCOPE (CLOSED HISTORY)

- This completed registration authorizes no product code or test edits/runs, Docker builds, deployment, runtime release or service changes, or operational data changes.
- No production DB, NAS, Jellyfin, download/retry/recovery, Writer socket, or Stage11 data writes or mutations.
- Do not change the common contract or existing Downloader, Discovery Writer Safety, or Stage11 contracts, active tasks, IDs, or evidence.
- Do not treat `STG9-MEDIA-001` as active; stop before Stage9 implementation until a separate user-approved task is registered with a validator-compatible ID.

### GOV-007 ACCEPTANCE_CRITERIA (CLOSED HISTORY)

- Governance router and active-work record show `INACTIVE / NONE`, version 1.0.0, and `REQUIRES_WORKSTREAMS: governance`.
- The canonical Stage9 registration commit is read back by exact SHA and contains the v1.0.0 approved contract, Stage9 `INACTIVE / NONE`, and the independent `stage9-media` route.
- The proposed `STG9-MEDIA-001` remains unapproved; current task-ID validation rejects that two-hyphen form, and no validation policy was changed.
- Downloader and Discovery Writer Safety remain `IN_PROGRESS / DLDWS-001` with `REQUIRES_WORKSTREAMS: downloader,discovery-writer-safety`; Stage11 remains `IN_PROGRESS / S11-WX011`.
- All-workstreams structure, governance smoke, existing task preflights, expected Governance rejection after closure, and `git diff --check` pass.
- Only governance documents changed; no product or operational changes occurred.

### GOV-007 EVIDENCE (CLOSED HISTORY)

- The user explicitly approved Governance activation and Stage9 Media governance registration on 2026-10-25. Verified canonical base: `e6e1a12eee6c8adfdb6bf09cdfe15ece34b6d515` on `teddy-subtitle-stage11`.
- Governance activation commit `5aed5316fbef0d6105fd0fd93798e322724522cd` was published by normal fast-forward from the verified base and read back as the exact canonical branch SHA. GOV-007 preflight passed during the active phase.
- Separate Stage9 registration commit `b28729e675232345825866caca3b455fc6484e51` was published by normal fast-forward from activation commit `5aed5316fbef0d6105fd0fd93798e322724522cd`. `git ls-remote` and the refreshed remote-tracking ref both reported the exact registration SHA; `git diff --exit-code` confirmed the fetched canonical tree matches it.
- Canonical readback confirmed the Stage9 contract and active-work paths, approved contract version 1.0.0, `stage9-media` router entry, and Stage9 `INACTIVE / NONE`. Downloader and Discovery Writer Safety remain `IN_PROGRESS / DLDWS-001`; Stage11 remains `IN_PROGRESS / S11-WX011`.
- GOV-007 is closed only after exact registration readback. No task-ID validator or common-contract policy was modified. `STG9-MEDIA-001` remains a proposal and is not runnable under the current one-hyphen task-ID format.
- Baseline and registration all-workstreams governance structure passed; governance smoke passed 21/21; DLDWS-001 and S11-WX011 preflights passed. GOV-007 preflight passed while active and is expected to reject after this closure.
- The previous DLDWS-001 registration evidence and archived pre-registration records remain preserved at `docs/governance/history/DLDWS-001-registration-base-34dede0/`; the existing workstream records and common contract were not modified.
- This registration and closure changed governance documents only. No product source, product tests, Docker build, runtime service, download, database, NAS, Jellyfin, or user data was changed.

### GOV-007 NEXT_DECISION (AT CLOSURE)

No Governance task is active. Before Stage9 implementation can be considered, the user must decide whether to separately approve a validator-compatible task ID or a Governance validation change for `STG9-MEDIA-001`, then approve the exact implementation and offline-verification scope. Production writes require additional explicit authorization.
