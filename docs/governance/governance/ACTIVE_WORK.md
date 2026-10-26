# Governance workstream — active work

WORKSTREAM: governance
TASK_ID: STG9MEDIA-001
STATUS: IN_PROGRESS
CONTRACT_VERSION: 1.0.0
REQUIRES_WORKSTREAMS: governance,downloader,discovery-writer-safety,stage9-media

## OBJECTIVE

Temporarily coordinate Governance, Downloader, Discovery Writer Safety, and Stage9 under the user-approved STG9MEDIA-001 integrated cutover; perform only the scoped governance activation/closure records and the approved Stage9 Media automation transition.

## APPROVED_SCOPE

- Record the user's 2026-10-26 joint authorization and temporary four-workstream route under STG9MEDIA-001.
- Permit only the specified generic-runner Stage9 Media opt-out, Stage9 dedicated runner promotion, live CT108 preflight, Stage9-only service/timer transition, first scheduled-run verification, and evidence/route restoration described in this task.
- Preserve Downloader DLDWS-001 and Discovery Writer Safety DLDWS-001 objectives, scopes, progress, candidates, and evidence; do not modify Writer socket implementation.
- Restore Governance to INACTIVE / NONE, Downloader and Discovery Writer Safety to DLDWS-001 with their original required workstream set, and Stage9 to STG9MEDIA-001 after completion or safe blocked closeout.
- Preserve the GOV-007 completion record below as historical evidence.

## PROHIBITED_SCOPE

- No common or workstream contract, validator, or CI policy changes.
- No Stage11 changes; no Writer socket implementation changes; no unrelated Downloader redesign or data cleanup.
- No operation outside the exact joint user-approved Stage9 Media transition. In particular, no other workstream deployment or data/service modification.
- If the active task cannot be validated jointly or an operational safety gate fails, stop operational changes and restore the original workstream routing without erasing evidence.

## ACCEPTANCE_CRITERIA

- The four selected workstreams have one matching task ID, `STG9MEDIA-001`, and each declares the full set `governance,downloader,discovery-writer-safety,stage9-media`.
- Joint preflight and structural/smoke checks pass before product or operational work.
- DLDWS-001 and S11-WX011 records and protected worktrees remain unchanged.
- On final closeout, Governance is `INACTIVE / NONE`; Downloader and Discovery Writer Safety are `IN_PROGRESS / DLDWS-001`; Stage9 is `IN_PROGRESS / STG9MEDIA-001`; their original required sets are restored.
- Any committed stage is normal fast-forwarded and exactly read back; no force push or unverified route transition.

## EVIDENCE

- User explicitly approved this one integrated transition on 2026-10-26 KST; canonical base SHA `7109e832aa4f38cda01cd1179b441a5a3aa18ab7` was verified on `teddy-subtitle-stage11` before joint activation.
- Temporary activation is limited to the four workstreams and current task identifier specified above; prior GOV-007 and DLDWS-001 history remains intact.

## NEXT_DECISION

After the integrated task reaches a verified outcome or a safety blocker, restore the original routing and record the exact completed/blocked boundary. This temporary Governance activation authorizes no unrelated governance work.

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
