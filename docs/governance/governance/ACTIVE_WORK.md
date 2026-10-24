# Governance workstream — active work

WORKSTREAM: governance
TASK_ID: GOV-007
STATUS: IN_PROGRESS
CONTRACT_VERSION: 1.0.0
REQUIRES_WORKSTREAMS: governance

## OBJECTIVE

Activate a single Governance task to register the independent `stage9-media` workstream and its approved design contract. The proposed Stage9 task ID `STG9-MEDIA-001` is not active and this registration grants no product implementation authority. Close GOV-007 after the separate registration commit is confirmed by exact canonical remote readback.

## APPROVED_SCOPE

- Activate GOV-007 in the Governance router and this active-work file, then verify its Governance preflight.
- Register `stage9-media` with its own v1.0.0 design contract, an `INACTIVE / NONE` active-work record, and an independent router entry.
- Record `STG9-MEDIA-001` as a proposed, unapproved task only; keep Stage9 `INACTIVE / NONE` so no implementation task is authorized.
- Route Stage9 media metadata, NFO/poster, and Jellyfin item-state behavior to `stage9-media`, carving that purpose-specific area out of the general Downloader route without changing Downloader task authorization.
- Preserve Downloader and Discovery Writer Safety `DLDWS-001`, Stage11 `S11-WX011`, their contracts, active records, and evidence; preserve the common project contract.
- Run governance-only structural and routing validation, existing task preflights, and `git diff --check`; publish activation, registration, and closure as normal fast-forward commits only after the expected canonical SHA is confirmed.
- Close GOV-007 and restore Governance to `INACTIVE / NONE` after exact remote readback of the Stage9 registration.

## PROHIBITED_SCOPE

- No Stage9 or other product source edits, product tests, Docker builds, deployment, runtime release changes, services or timers, downloads or recovery.
- No production database, NAS, Jellyfin, Writer socket, or other operational writes or mutations.
- Do not change the common project contract, Downloader or Discovery Writer Safety contracts/active-work records, `DLDWS-001` state or evidence, or Stage11 contract/code/`S11-WX011`.
- Do not modify existing candidate worktrees or Git history; do not reset, clean, rebase, merge, or force-push. Stop on any remote SHA drift or failed required check.
- This task does not authorize implementation under `STG9-MEDIA-001`; obtain a separate explicit user approval before activating that task or changing product files.

## ACCEPTANCE_CRITERIA

- GOV-007 passes Governance preflight only while Governance is `IN_PROGRESS / GOV-007`; after closure Governance returns to `INACTIVE / NONE`.
- The Stage9 contract and active-work file are present at the exact registered paths, agree on contract version 1.0.0, and the router independently registers `stage9-media`.
- Stage9 remains `INACTIVE / NONE`; `STG9-MEDIA-001` is explicitly marked proposed and unapproved, with implementation authorization `NO`.
- The Downloader route excludes the newly assigned Stage9 Media purpose; Downloader and Discovery Writer Safety remain exactly `IN_PROGRESS / DLDWS-001` with `REQUIRES_WORKSTREAMS: downloader,discovery-writer-safety`; Stage11 remains exactly `IN_PROGRESS / S11-WX011`.
- All-workstream governance structure, governance smoke, Downloader + Discovery Writer Safety preflight, Stage11 preflight, GOV-007 preflight at the active stage, and `git diff --check` pass. No product-specific tests run.
- Activation, Stage9 registration, and Governance closure are separate normal fast-forward commits; each push starts from the exact verified remote SHA and each final tree is confirmed by exact canonical SHA readback.
- No product or operational changes occur.

## EVIDENCE

- Existing shared DLDWS-001 registration commit `6014164c395be31fe4bb30c32062e1a3be08d37f` was previously read back from the canonical branch with Governance, Downloader, and Discovery Writer Safety participating.
- Existing Governance, Downloader, and Discovery Writer Safety records were read back as `IN_PROGRESS / DLDWS-001`, contract version `1.0.0`, with `REQUIRES_WORKSTREAMS: governance,downloader,discovery-writer-safety` at registration.
- Stage11 active-work blob `39b7440f92c38e406a2aa1b0d266d1cab5ddc848` was preserved in the prior registration, and the complete pre-registration Governance, Downloader, Discovery Writer Safety, and router records remain archived at `docs/governance/history/DLDWS-001-registration-base-34dede0/`.
- Prior DLDWS-001 registration and closure changed governance documents only; no product code, product tests, Docker build, service, socket, download, or operational data was changed.
- User explicitly approved Governance activation and Stage9 Media governance registration on 2026-10-25. Canonical base and freshly rechecked `origin/teddy-subtitle-stage11` SHA: `e6e1a12eee6c8adfdb6bf09cdfe15ece34b6d515`. A clean isolated clone was created at `/tmp/downloader-stage9-media-registration-20261025`; the existing dirty worktree was not touched.
- GOV-007 is the next available Governance task ID: prior active/history records use GOV-001 through GOV-006; no GOV-007 occurrence exists in the canonical base tree or history. `STG9-MEDIA-001` likewise has no prior registration or use in the canonical base.
- Baseline all-workstreams structural validation passed; governance smoke passed 21/21; DLDWS-001 and S11-WX011 preflights passed. Governance GOV-007 preflight failed as expected while Governance was `INACTIVE / NONE`.
- This activation phase changes only the Governance router and Governance active-work metadata.

## NEXT_DECISION

Complete the approved Stage9 registration and exact remote readback, then close GOV-007. Keep Stage9 inactive until the user separately approves a task for implementation; no product implementation is authorized by this registration.
