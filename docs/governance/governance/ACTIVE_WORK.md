# Governance workstream — active work

WORKSTREAM: governance
TASK_ID: NONE
STATUS: INACTIVE
CONTRACT_VERSION: 1.0.0
REQUIRES_WORKSTREAMS: governance

## OBJECTIVE

GOV-007 completed the approved independent Stage9 Media governance registration and is closed after exact canonical remote readback. No Governance task is currently active.

## APPROVED_SCOPE

- Register the `stage9-media` workstream with its approved v1.0.0 design contract, independent router entry, and `INACTIVE / NONE` active-work record.
- Record `STG9-MEDIA-001` only as a proposed, unapproved identifier; Stage9 implementation remains unauthorized and inactive.
- Route Stage9 Media metadata/NFO/poster/Jellyfin item-state behavior away from the generic Downloader area while preserving Downloader `DLDWS-001`, Discovery Writer Safety `DLDWS-001`, and Stage11 `S11-WX011`.
- Restore Governance to `INACTIVE / NONE` after exact canonical readback of the separate Stage9 registration commit.

## PROHIBITED_SCOPE

- This completed registration authorizes no product code or test edits/runs, Docker builds, deployment, runtime release or service changes, or operational data changes.
- No production DB, NAS, Jellyfin, download/retry/recovery, Writer socket, or Stage11 data writes or mutations.
- Do not change the common contract or existing Downloader, Discovery Writer Safety, or Stage11 contracts, active tasks, IDs, or evidence.
- Do not treat `STG9-MEDIA-001` as active; stop before Stage9 implementation until a separate user-approved task is registered with a validator-compatible ID.

## ACCEPTANCE_CRITERIA

- Governance router and active-work record show `INACTIVE / NONE`, version 1.0.0, and `REQUIRES_WORKSTREAMS: governance`.
- The canonical Stage9 registration commit is read back by exact SHA and contains the v1.0.0 approved contract, Stage9 `INACTIVE / NONE`, and the independent `stage9-media` route.
- The proposed `STG9-MEDIA-001` remains unapproved; current task-ID validation rejects that two-hyphen form, and no validation policy was changed.
- Downloader and Discovery Writer Safety remain `IN_PROGRESS / DLDWS-001` with `REQUIRES_WORKSTREAMS: downloader,discovery-writer-safety`; Stage11 remains `IN_PROGRESS / S11-WX011`.
- All-workstreams structure, governance smoke, existing task preflights, expected Governance rejection after closure, and `git diff --check` pass.
- Only governance documents changed; no product or operational changes occurred.

## EVIDENCE

- The user explicitly approved Governance activation and Stage9 Media governance registration on 2026-10-25. Verified canonical base: `e6e1a12eee6c8adfdb6bf09cdfe15ece34b6d515` on `teddy-subtitle-stage11`.
- Governance activation commit `5aed5316fbef0d6105fd0fd93798e322724522cd` was published by normal fast-forward from the verified base and read back as the exact canonical branch SHA. GOV-007 preflight passed during the active phase.
- Separate Stage9 registration commit `b28729e675232345825866caca3b455fc6484e51` was published by normal fast-forward from activation commit `5aed5316fbef0d6105fd0fd93798e322724522cd`. `git ls-remote` and the refreshed remote-tracking ref both reported the exact registration SHA; `git diff --exit-code` confirmed the fetched canonical tree matches it.
- Canonical readback confirmed the Stage9 contract and active-work paths, approved contract version 1.0.0, `stage9-media` router entry, and Stage9 `INACTIVE / NONE`. Downloader and Discovery Writer Safety remain `IN_PROGRESS / DLDWS-001`; Stage11 remains `IN_PROGRESS / S11-WX011`.
- GOV-007 is closed only after exact registration readback. No task-ID validator or common-contract policy was modified. `STG9-MEDIA-001` remains a proposal and is not runnable under the current one-hyphen task-ID format.
- Baseline and registration all-workstreams governance structure passed; governance smoke passed 21/21; DLDWS-001 and S11-WX011 preflights passed. GOV-007 preflight passed while active and is expected to reject after this closure.
- The previous DLDWS-001 registration evidence and archived pre-registration records remain preserved at `docs/governance/history/DLDWS-001-registration-base-34dede0/`; the existing workstream records and common contract were not modified.
- This registration and closure changed governance documents only. No product source, product tests, Docker build, runtime service, download, database, NAS, Jellyfin, or user data was changed.

## NEXT_DECISION

No Governance task is active. Before Stage9 implementation can be considered, the user must decide whether to separately approve a validator-compatible task ID or a Governance validation change for `STG9-MEDIA-001`, then approve the exact implementation and offline-verification scope. Production writes require additional explicit authorization.
