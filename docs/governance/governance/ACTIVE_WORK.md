# Governance workstream — active work

WORKSTREAM: governance
TASK_ID: DWS-001
STATUS: IN_PROGRESS
CONTRACT_VERSION: 1.0.0
REQUIRES_WORKSTREAMS: governance,discovery-writer-safety

## OBJECTIVE

Use temporary user-approved Governance participation to register DWS-001 as the same shared task ID in Governance and Discovery Writer Safety. Read back the exact registration on the canonical remote, then close Governance alone; DWS-001 stays active in its independent workstream.

## APPROVED_SCOPE

- Change the workstream routing registry and both Governance and Discovery Writer Safety ACTIVE_WORK records for the shared DWS-001 registration.
- Verify exact canonical remote readback with both workstreams IN_PROGRESS / DWS-001 and the complete REQUIRES_WORKSTREAMS: governance,discovery-writer-safety set.
- After registration readback, restore Governance INACTIVE / NONE and leave Discovery Writer Safety IN_PROGRESS / DWS-001 under only its own workstream.
- Preserve previous GOV-005 history, the approved v1.0.0 contracts, and existing DL-001 and S11-WX011 state.
- Update the existing canonical handoff with important registration and closure evidence.

## PROHIBITED_SCOPE

- No Writer product code, existing Writer smoke, synthetic socket reproduction, Docker build, or production deployment during shared registration.
- No changes to DL-001, S11-WX011, their contracts, source files, or existing candidates.
- No production socket probing/removal, Writer restart, downloads/retries/remux, operational files, service state, database, NAS/Jellyfin, or user-data changes.
- No new Governance ID, no reuse of closed GOV IDs, and no Writer design or implementation authorization inferred from registration.

## ACCEPTANCE_CRITERIA

- Canonical remote shows Governance and Discovery Writer Safety both IN_PROGRESS / DWS-001 with matching full REQUIRES_WORKSTREAMS in router and ACTIVE_WORK files.
- Exact shared-registration remote readback precedes Governance closure.
- Final state has Governance INACTIVE / NONE and Discovery Writer Safety IN_PROGRESS / DWS-001 with only discovery-writer-safety required.
- Downloader DL-001, Stage11 S11-WX011, all approved contracts, product code and existing evidence remain unchanged.
- The canonical handoff preserves both registration and closure evidence. Any unavailable runtime/structural check is reported as unverified.

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
- The GOV-005 activation commit `68d25dc2626ea3edd687925dea85565102283fd7` was read back from canonical `teddy-subtitle-stage11` with Governance IN_PROGRESS / GOV-005 before adding the new workstream.
- Baseline checks at the approved base passed for all-workstreams structure, governance smoke (21/21), Downloader DL-001 preflight, and Stage11 S11-WX011 preflight. Governance GOV-005 preflight correctly failed before activation because Governance was INACTIVE / NONE.
- After registering the inactive workstream candidate, the all-workstreams check, Governance GOV-005 preflight, Downloader DL-001 preflight, Stage11 S11-WX011 preflight, and governance smoke (21/21) passed. DWS-001 preflight correctly rejected the inactive workstream.
- No product code, Writer smoke, DL-001 candidate, Stage11 files, or production resources are in GOV-005 scope.
- Registration commit `33432e965292610e3cfe3f909438ec2fe5fe588b` was read back from canonical `teddy-subtitle-stage11`: discovery-writer-safety contract v1.0.0 APPROVED and ACTIVE_WORK INACTIVE / NONE. Its route is limited to Writer socket lifecycle/stale-socket safety; other non-subtitle Discovery remains Downloader-owned.
- Final all-workstreams validation, governance smoke (21/21), Downloader DL-001 preflight, Stage11 S11-WX011 preflight, and `git diff --check` passed before closure. Governance GOV-005 and DWS-001 preflights both rejected their tasks after closure/inactive registration as expected.
- GOV-005 closure restores Governance to INACTIVE / NONE. Downloader DL-001 and Stage11 S11-WX011 are preserved. No product code, Writer smoke, Docker, production service, socket, database, download, NAS/Jellyfin, or user data was changed.
- 2026-10-19: The user explicitly approved option A, using the same DWS-001 task ID shared by Governance and Discovery Writer Safety, registration remote readback, then Governance-only closure. Subsequent read-only Writer inspection and isolated synthetic Unix socket reproduction are approved solely under active DWS-001; no product or operational changes.

## NEXT_DECISION

Read back the shared registration from canonical GitHub, then close Governance only. Socket investigation may begin under DWS-001 only after that closure.
