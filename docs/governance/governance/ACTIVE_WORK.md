# Governance workstream — active work

WORKSTREAM: governance
TASK_ID: GOV-005
STATUS: IN_PROGRESS
CONTRACT_VERSION: 1.0.0
REQUIRES_WORKSTREAMS: governance

## OBJECTIVE

Register the approved discovery-writer-safety workstream with a narrowly routed contract and inactive initial task state, then close GOV-005 and restore Governance to INACTIVE / NONE.

## APPROVED_SCOPE

- Activate GOV-005 in Governance and validate its task registration.
- Add the approved discovery-writer-safety v1.0.0 contract and an INACTIVE / NONE ACTIVE_WORK file.
- Route only Discovery Writer Unix socket lifecycle and stale-socket safety to the new workstream; leave other non-subtitle Discovery in Downloader.
- Preserve Downloader DL-001 and Stage11 S11-WX011 without editing their contracts or ACTIVE_WORK files.
- Run the existing governance, Downloader, and Stage11 checks; record safe registration evidence in the canonical handoff.
- Close GOV-005 after successful registration readback and restore Governance to INACTIVE / NONE.

## PROHIBITED_SCOPE

- Do not modify product code, teddy_library_discovery_writer.py, Writer smoke tests, or the DL-001 implementation candidate.
- Do not run socket-reproduction tests or build Docker images.
- Do not change Downloader or Stage11 contracts, ACTIVE_WORK files, or task states.
- Do not change production services, operational download jobs, NAS/Jellyfin data, or user files.
- Do not activate DWS-001 as part of GOV-005.

## ACCEPTANCE_CRITERIA

- GOV-005 preflight passes before registration work; final Governance router and ACTIVE_WORK are INACTIVE / NONE with REQUIRES_WORKSTREAMS: governance.
- The new route points to the new v1.0.0 APPROVED contract and INACTIVE / NONE ACTIVE_WORK file.
- The new route covers only Writer Unix socket lifecycle/stale cleanup safety; all other non-subtitle Discovery remains in Downloader.
- All-workstreams governance validation and smoke, Downloader DL-001 preflight, Stage11 S11-WX011 preflight, and git diff --check pass.
- GOV-005 is rejected by Governance preflight after closure; DWS-001 is not runnable while the new workstream is INACTIVE / NONE.
- Downloader DL-001 and Stage11 S11-WX011 remain unchanged; historical GOV-001 through GOV-004 evidence remains preserved.
- Remote readback confirms registration and closure; no product or production changes occur.

## EVIDENCE


- GOV-001 candidate was applied to the canonical branch and the approved common/domain contracts were recorded under GOV-002; prior handoff history is preserved.
- GOV-003 completed the 2026-10-16 Stage11 contract state-paragraph alignment. Its ID and history were preserved and not reused.
- GOV-004 was user-approved on 2026-10-17. Its registration commit `d64da2011c33b2b1f7f9c9d46355145025dbb278` was read back from canonical `teddy-subtitle-stage11` before applying the approved Downloader contract and route.
- Before DL-001 registration, Downloader v1.0.0 was APPROVED and INACTIVE / NONE; its contract requires globally serialized MP4 remux/conversion independently of download concurrency.
- GOV-004 validation passed: all-workstreams structural check, governance smoke 21/21, Stage11 S11-WX011 preflight, and `git diff --check`. It made no product or operational changes.
- User approved Governance and Downloader sharing DL-001 for registration on 2026-10-17. The shared-registration commit `eebe6a22f2d102e85e4638c21a91f0a1189c4c4e` was read back from the canonical branch with both workstreams at IN_PROGRESS / DL-001 and REQUIRES_WORKSTREAMS: governance,downloader.
- Shared preflight, all-workstreams structural validation, governance smoke (21/21), Stage11 S11-WX011 preflight, and `git diff --check` passed before shared registration was applied.
- Governance participation was closed after shared registration readback. Downloader remains IN_PROGRESS / DL-001 with REQUIRES_WORKSTREAMS: downloader. No product code, operational files, services, real downloads, retries, NAS/Jellyfin data, or user files were changed.
- User approved GOV-005 for registering discovery-writer-safety on 2026-10-19. Canonical base SHA: `30fb83e1c6b2a80eee67cef5bac8192bf6fa719b`.
- Baseline checks at the approved base passed for all-workstreams structure, governance smoke (21/21), Downloader DL-001 preflight, and Stage11 S11-WX011 preflight. Governance GOV-005 preflight correctly failed before activation because Governance was INACTIVE / NONE.
- No product code, Writer smoke, DL-001 candidate, Stage11 files, or production resources are in GOV-005 scope.

## NEXT_DECISION

After registration and closure are read back from the canonical remote, DWS-001 remains INACTIVE / NONE until separately activated and approved.
