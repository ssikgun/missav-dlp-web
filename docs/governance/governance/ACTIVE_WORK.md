# Governance workstream — active work

WORKSTREAM: governance
TASK_ID: DLDWS-001
STATUS: IN_PROGRESS
CONTRACT_VERSION: 1.0.0
REQUIRES_WORKSTREAMS: governance,downloader,discovery-writer-safety

## OBJECTIVE

Register DLDWS-001 as the shared governance task for safely investigating the DL-001 Writer smoke blocker with Discovery Writer Safety, preserve each prior task record and evidence, verify the exact shared registration on the canonical remote, then close Governance participation in a separate commit.

## APPROVED_SCOPE

- Update only the routing registry and Governance, Downloader, and Discovery Writer Safety active-work records for the shared DLDWS-001 registration.
- Preserve the complete pre-registration router, GOV-006, DL-001, and DWS-001 active records as exact archived files with their base commit and Git blob SHAs.
- Verify that all three active records have the same task ID, status, contract version, and exact `REQUIRES_WORKSTREAMS` value.
- Run the required structural check, shared-task preflight, Stage11 preflight, governance smoke, and `git diff --check` on an isolated worktree.
- Publish the registration with a normal fast-forward push only after checking the remote SHA; read back the exact commit and affected files from GitHub.
- After exact registration readback, close Governance in a separate commit while preserving the shared Downloader and Discovery Writer Safety task and the independent Stage11 task.

## PROHIBITED_SCOPE

- This registration and closure execution does not authorize product-code or test changes, Docker builds, service or socket changes, deployments, or operational data access or modification.
- Do not delete, weaken, bypass, or alter test success criteria.
- Do not change DL-001, DWS-001, GOV-006, or S11-WX011 history or evidence except to preserve the prior active records in the named archive.
- Do not modify Stage11 files, existing dirty worktrees, downloads, `.parts`, TS/MP4 files, task state, NAS, Jellyfin, or operational Writer resources.
- Do not reset, clean, rebase, merge, or force-push. Stop if the remote base changes or any required check/readback fails.

## ACCEPTANCE_CRITERIA

- Governance, Downloader, and Discovery Writer Safety are all `IN_PROGRESS / DLDWS-001`, contract version `1.0.0`, with exactly `governance,downloader,discovery-writer-safety` in `REQUIRES_WORKSTREAMS`.
- Stage11 remains unchanged at its previously registered task and status.
- The previous router, GOV-006, DL-001, and DWS-001 active records are preserved byte-for-byte with restoration commit and blob SHAs.
- All-workstreams structure, DLDWS-001 shared preflight, Stage11 preflight, governance smoke, and `git diff --check` pass.
- The registration is confirmed by exact GitHub readback before a separate Governance closure commit is prepared.
- The final remote state is Governance `INACTIVE / NONE`, with Downloader and Discovery Writer Safety sharing `DLDWS-001`; no product or operational work is implied by Governance closure.

## EVIDENCE

- The approved GOV-006 activation is present at canonical base `34dede0af5bc205ff11af4275727e11627de680b`.
- Baseline checks at that base passed: all-workstreams structure; Governance GOV-006, Downloader DL-001, Discovery Writer Safety DWS-001, and Stage11 S11-WX011 preflights; governance smoke (21/21); and `git diff --check`.
- Exact pre-registration records and restoration identifiers are preserved under `docs/governance/history/DLDWS-001-registration-base-34dede0/`.
- Shared registration publication/readback and Governance closure are pending in this active stage. No product code, tests, Docker build, service, socket, download, or operational data has been changed by this registration task.

## NEXT_DECISION

Complete the shared registration commit and exact canonical readback. Only then prepare the separate Governance-closure commit. Any later product, test, offline integration, or Docker candidate verification work requires an execution scope that explicitly authorizes those actions.
