# Governance workstream — active work

WORKSTREAM: governance
TASK_ID: NONE
STATUS: INACTIVE
CONTRACT_VERSION: 1.0.0
REQUIRES_WORKSTREAMS: governance

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
