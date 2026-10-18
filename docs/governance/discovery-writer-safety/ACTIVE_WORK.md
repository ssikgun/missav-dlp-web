# Discovery Writer Safety workstream — active work

WORKSTREAM: discovery-writer-safety
TASK_ID: DWS-001
STATUS: IN_PROGRESS
CONTRACT_VERSION: 1.0.0
REQUIRES_WORKSTREAMS: governance,discovery-writer-safety

## OBJECTIVE

After shared registration readback and Governance closure, investigate the Discovery Writer Unix socket lifecycle and inode-reuse/path-replacement safety using read-only source inspection and bounded isolated synthetic socket races. Identify evidence and compare safe solutions, without modifying the product.

## APPROVED_SCOPE

- Read-only inspect the existing Writer Unix socket lifecycle code, existing smoke tests, and prior reported socket-identity/race failures.
- After Governance-only closure, use synthetic Unix sockets under a disposable isolated test-only directory to examine inode reuse, stale socket cleanup, active listener protection, replacement after probe, replacement immediately before unlink, and forced termination/restart.
- Preserve unrelated current source, the DL-001 implementation candidate, original failed-job fragments, and S11-WX011 artifacts.
- Distinguish reproducible observed failures from hypothetical risks, report PASS/FAIL/UNKNOWN case-by-case, and compare lifecycle lock versus socket activation or other safe designs.
- Produce investigation evidence and a reviewable design recommendation only; actual Writer code/test changes require separate explicit user approval.

## PROHIBITED_SCOPE

- No product Writer code or existing smoke changes, no test bypass, and no implementation or selection of a production design under this task.
- No real Writer socket probe/unlink/replacement, service restart, Docker build, production deployment, or real download/retry/remux/recovery.
- No access or changes to operational .tasks/.settings, failed-job .parts/TS/MP4, databases, NAS/Jellyfin, operational files, or user data.
- No changes to Downloader/DL-001, Stage11/S11-WX011, model environments, or existing candidates; no changes to approved workstream contracts.
- No synthetic race execution until shared registration remote readback and Governance closure.

## ACCEPTANCE_CRITERIA

- Shared DWS-001 registration with Governance has exact remote readback before Governance-only closure; afterward this task alone is IN_PROGRESS in router and ACTIVE_WORK with REQUIRES_WORKSTREAMS: discovery-writer-safety.
- Read-only review identifies Writer liveness, identity and unlink boundaries and correlates them with existing evidence.
- The approved isolated synthetic cases are reproduced/tested in disposable test-only directories, with observed and unverified cases clearly distinguished and no claim of operational safety without supporting evidence.
- Safe design options are compared and reported, without changing Writer source or smoke unless separately approved.
- DL-001 and S11-WX011, original evidence, operating state, and all production data remain unchanged.

## EVIDENCE

- This workstream was registered under user-approved GOV-005 on 2026-10-19.
- GOV-005 registers this workstream only; it does not activate DWS-001 or authorize product, socket, database, or production work.
- 2026-10-19: User explicitly approved shared DWS-001 registration with Governance and Discovery Writer Safety, canonical remote readback, Governance-only closure, then read-only Writer analysis and isolated synthetic socket reproduction. Product and operational changes remain prohibited.

## NEXT_DECISION

Complete exact shared registration readback and Governance-only closure, then start bounded read-only source inspection and isolated synthetic socket reproduction. Return design choices for user approval before any Writer implementation.
