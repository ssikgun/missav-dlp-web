# Governance workstream — active work

WORKSTREAM: governance
TASK_ID: DL-001
STATUS: IN_PROGRESS
CONTRACT_VERSION: 1.0.0
REQUIRES_WORKSTREAMS: governance,downloader

## OBJECTIVE

Register the user-approved DL-001 as a shared Governance and Downloader task, verify and read it back from the canonical branch, then close Governance participation while leaving DL-001 active only in Downloader.

## APPROVED_SCOPE

- Register the same DL-001 task ID in Governance and Downloader and align the routing registry with both ACTIVE_WORK files.
- Run the shared registration preflight, structural validation, governance smoke, and diff checks.
- Apply the approved registration documents to `teddy-subtitle-stage11` and verify the remote readback.
- After shared-registration readback passes, close Governance participation, record the registration and closure evidence, and leave Downloader active with DL-001.
- Update the existing canonical handoff with concise registration evidence.

## PROHIBITED_SCOPE

- Do not modify product code or start Downloader implementation during this Governance registration task.
- Do not change production services or Stage11 contracts, state, code, or artifacts.
- Do not retry downloads, recover real MP4 jobs, write to NAS/Jellyfin, or delete or move data.
- Do not alter Docker or Proxmox configuration or bypass remote protections.

## ACCEPTANCE_CRITERIA

- During registration, Governance and Downloader both show `IN_PROGRESS / DL-001`, and both ACTIVE_WORK files declare `REQUIRES_WORKSTREAMS: governance,downloader`.
- The shared-workstream authorization check, all-workstreams structural check, governance smoke, and `git diff --check` pass.
- The canonical remote readback confirms the shared DL-001 registration before Governance is closed.
- Final Governance is `INACTIVE / NONE`; final Downloader is `IN_PROGRESS / DL-001` with its approved task scope intact.
- Final all-workstreams validation, Downloader task preflight, Stage11 S11-WX011 preflight, governance smoke, and diff check pass.
- Stage11 remains unchanged; product code, operational files, real downloads, NAS, and user data are not modified.

## EVIDENCE

- GOV-001 candidate was applied to the canonical branch and the approved common/domain contracts were recorded under GOV-002; prior handoff history is preserved.
- GOV-003 completed the 2026-10-16 Stage11 contract state-paragraph alignment. Its ID and history were preserved and not reused.
- GOV-004 was user-approved on 2026-10-17. Its registration commit `d64da2011c33b2b1f7f9c9d46355145025dbb278` was read back from canonical `teddy-subtitle-stage11` before applying the approved Downloader contract and route.
- Before DL-001 registration, Downloader v1.0.0 was APPROVED and INACTIVE / NONE; the contract requires globally serialized MP4 remux/conversion independently of download concurrency.
- GOV-004 validation passed (all-workstreams structural check, governance smoke 21/21, Stage11 S11-WX011 task preflight, and `git diff --check`); no product or operational changes occurred.
- The prior Stage11 contract and ACTIVE_WORK were unchanged at IN_PROGRESS / S11-WX011; GOV-001 through GOV-003 history was preserved.
- GOV-004 made no product or operational changes: no retries, data deletions, service/Proxmox changes, NAS/Jellyfin writes, or deployment.
- User approved Governance and Downloader sharing DL-001 for registration on 2026-10-17; this phase authorizes registration only.
- Canonical base HEAD verified as `90abfbbfeef9a6e2dc532ad4cd0cefd9b31fe82f`; DL-001 appeared only as an inactive proposal before registration.
- GOV-001, GOV-002, GOV-003, and GOV-004 histories remain preserved and their IDs are not reused.

## NEXT_DECISION

After shared registration readback, close Governance participation, verify the final canonical state, and leave product implementation for the separately approved Downloader phase.
