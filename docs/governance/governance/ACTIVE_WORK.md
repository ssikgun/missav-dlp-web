# Governance workstream — active work

WORKSTREAM: governance
TASK_ID: NONE
STATUS: INACTIVE
CONTRACT_VERSION: 1.0.0
REQUIRES_WORKSTREAMS: governance

## OBJECTIVE

The temporary shared Governance + Stage9 task `STG9MEDIA-001` is complete and closed after exact canonical readback. No Governance task is currently active.

## APPROVED_SCOPE

- The closed task corrected exactly two stale task-state descriptions in the Stage9 v1.0.0 contract.
- Governance was activated jointly with Stage9 under `STG9MEDIA-001` and is now restored to `INACTIVE / NONE`.
- Stage9 remains `IN_PROGRESS / STG9MEDIA-001` with its original single-workstream requirement and contract-change prohibition restored.
- The prior GOV-007 completion record is preserved below as historical evidence.

## PROHIBITED_SCOPE

- This Governance task is closed and grants no further authorization.
- No product source, candidate, product tests, database migration, operational data access/write, service or timer change, deployment, download, NAS, or Jellyfin operation was authorized or performed.
- No common contract, validator/CI, other workstream contract/task, or Stage9 design policy was changed.

## ACCEPTANCE_CRITERIA

- Canonical router reports Governance `INACTIVE / NONE` and Stage9 `IN_PROGRESS / STG9MEDIA-001`.
- Governance ACTIVE_WORK requires only `governance`; Stage9 ACTIVE_WORK requires only `stage9-media`.
- The two approved Stage9 contract status descriptions were corrected; version remains 1.0.0 and status remains APPROVED.
- All-workstreams structure, Stage9 and protected-workstream preflights, governance smoke, and `git diff --check` pass; Governance inactive preflight is rejected as expected.
- The closure commit is published by normal fast-forward and exactly read back.

## EVIDENCE

- User approved the temporary shared Governance + Stage9 correction on 2026-10-25 under the existing task ID `STG9MEDIA-001`; base SHA was `0f1373171a4a384aadc3549d9cd0e12a0e2a6317`.
- Joint activation commit `9ab50b13b69f1ee30cc31135f60685bbcf43be6b` was published by fast-forward and its three active-work records were exactly read back.
- Contract correction commit `fd6af7f14a1cf988f574e5c862b026d40057d30d` was published by fast-forward and exactly read back; only the two approved state descriptions changed.
- GOV-007 completion history is retained below without current authorization.
- The closure commit containing this record will be verified by exact canonical remote SHA and byte-for-byte readback.

## NEXT_DECISION

Governance is inactive. Stage9 remains active under `STG9MEDIA-001`. The previously blocked offline migration rehearsal requires a separate user instruction; this closed Governance correction authorizes no migration or implementation.

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
