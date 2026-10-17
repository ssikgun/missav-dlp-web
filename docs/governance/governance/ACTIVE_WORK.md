# Governance workstream — active work

WORKSTREAM: governance
TASK_ID: GOV-004
STATUS: IN_PROGRESS
CONTRACT_VERSION: 1.0.0
REQUIRES_WORKSTREAMS: governance

## OBJECTIVE

Register and approve the independently scoped non-subtitle Downloader workstream in the canonical routing registry, while preserving the completed GOV-001, GOV-002, and GOV-003 history and the active Stage11 task.

## APPROVED_SCOPE

- Review and apply the user-reviewed Downloader workstream candidate.
- Approve the Downloader PROJECT_CONTRACT v1.0.0, including globally serial MP4 remux/conversion: one job at a time, independently of configured download concurrency; changing this policy requires explicit user approval.
- Add the Downloader route and inactive Downloader ACTIVE_WORK record.
- Run governance structure checks, smoke checks, and the specified authorization-denial checks.
- Record GOV-004 registration and closure in the existing canonical handoff, then restore Governance to INACTIVE / NONE.
- Apply only approved governance/Downloader registration documents to canonical `teddy-subtitle-stage11` after remote-head checks and verify remote readback.

## PROHIBITED_SCOPE

- Do not modify Downloader product code or operational configuration.
- Do not alter Stage11 code, contract, ACTIVE_WORK, artifacts, model environment, or S11-WX011 state.
- Do not restart services, retry downloads, convert MP4 files, move or delete download data, write to NAS/Jellyfin, change Proxmox, or deploy.
- Do not change the common project contract, governance enforcement, or any unrelated workstream contract.
- Do not reuse or rewrite the completed GOV-001, GOV-002, or GOV-003 history.
- Do not activate DL-001 or infer implementation authorization from this registration.

## ACCEPTANCE_CRITERIA

- GOV-004 is registered as `IN_PROGRESS` in both the Governance router and Governance ACTIVE_WORK before downstream registration changes.
- Governance task preflight for GOV-004 passes before contract or Downloader route changes.
- Downloader contract is v1.0.0 / APPROVED and states global one-at-a-time MP4 remux/conversion separately from download concurrency.
- Downloader router and ACTIVE_WORK both end at INACTIVE / NONE; Stage11 remains IN_PROGRESS / S11-WX011 unchanged.
- All-workstreams structure validation, governance smoke, `git diff --check`, Stage11 task preflight, and DL-001 denial pass.
- Only authorized governance/Downloader registration documents change; canonical remote readback confirms the final states.
- GOV-004 is closed with Governance restored to INACTIVE / NONE, and its evidence is recorded in the handoff.

## EVIDENCE

- User approved this registration and contract approval under GOV-004 on 2026-10-17; product implementation, operational recovery, and deployment remain excluded.
- Base canonical `teddy-subtitle-stage11` SHA: `45981e12f405e56498fc72f3f2d6ddc9cc740e0d`; latest fetched remote SHA matched this base before worktree creation.
- GOV-004 did not appear in the inspected current router, active-work records, handoff, or reachable Git commit subjects before registration.
- GOV-003 remains the completed 2026-10-16 Stage11 contract state-paragraph alignment task; GOV-001 and GOV-002 history is unchanged.
- The user-reviewed local candidate is preserved at `/tmp/downloader-registration-candidate-20261017`; this task uses a separate clean worktree.

## NEXT_DECISION

After GOV-004 registration is verified from canonical remote, apply the approved Downloader contract and inactive route, run final validation, close GOV-004, and verify the final remote readback. DL-001 requires a separate user-approved task and registration.
