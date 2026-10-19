# Discovery Writer Safety workstream — active work

WORKSTREAM: discovery-writer-safety
TASK_ID: DWS-001
STATUS: IN_PROGRESS
CONTRACT_VERSION: 1.0.0
REQUIRES_WORKSTREAMS: discovery-writer-safety

## OBJECTIVE

Investigate and address Discovery Writer Unix socket lifetime races under the explicitly user-approved B option: implement a systemd socket-activation code candidate and strictly isolated offline tests, retaining all operational safeguards. DWS-001 remains independent of DL-001 MP4 serialization and S11-WX011.

## APPROVED_SCOPE

- Read-only inspect the existing Writer Unix socket lifecycle code, existing smoke tests, and prior reported socket-identity/race failures.
- After Governance-only closure, use synthetic Unix sockets under a disposable isolated test-only directory to examine inode reuse, stale socket cleanup, active listener protection, replacement after probe, replacement immediately before unlink, and forced termination/restart.
- Preserve unrelated current source, the DL-001 implementation candidate, original failed-job fragments, and S11-WX011 artifacts.
- Distinguish reproducible observed failures from hypothetical risks, report PASS/FAIL/UNKNOWN case-by-case, and compare lifecycle lock versus socket activation or other safe designs.
- Following the user's explicit 2026-10-19 B-option approval, implement Writer systemd socket-activation handling and associated scoped test changes in an isolated candidate branch/worktree only, after remote task-scope readback; keep the currently deployed Writer untouched.
- Develop an offline socket-unit/service-integration candidate without applying it to systemd or assuming unknown live unit settings. Validate inherited listening fd type, PID/count/path, no unlink, active listener safety, and restart semantics using synthetic sockets only.
- Preserve existing direct-mode safety regressions and distinguish any remaining legacy race failure from B-mode success. Report incompatible or unknown deployment details as blocked for later separate approval.

## PROHIBITED_SCOPE

- Product Writer code and scoped Writer smoke/test edits are permitted only as a reviewable, isolated B-option systemd socket-activation candidate under the user's new explicit approval. No unrelated code changes, broad test bypass, automatic production selection, or deployment are permitted.
- No real Writer socket probe/unlink/replacement, service restart, Docker build, production deployment, or real download/retry/remux/recovery.
- No access or changes to operational .tasks/.settings, failed-job .parts/TS/MP4, databases, NAS/Jellyfin, operational files, or user data.
- No changes to Downloader/DL-001, Stage11/S11-WX011, model environments, or existing candidates; no changes to approved workstream contracts.
- No production execution of new socket activation or changes to existing installed systemd unit/service settings; no Git merge to the deployed release or CT108's dirty Stage11 worktree.

## ACCEPTANCE_CRITERIA

- Shared DWS-001 registration with Governance has exact remote readback before Governance-only closure; afterward this task alone is IN_PROGRESS in router and ACTIVE_WORK with REQUIRES_WORKSTREAMS: discovery-writer-safety.
- Read-only review identifies Writer liveness, identity and unlink boundaries and correlates them with existing evidence.
- The approved isolated synthetic cases are reproduced/tested in disposable test-only directories, with observed and unverified cases clearly distinguished and no claim of operational safety without supporting evidence.
- Original safe-design investigation evidence is preserved. Under the subsequent user-approved B scope, a candidate supports inherited systemd listener sockets without Writer-side unlink and has strictly isolated synthetic tests and fail-closed validation. Any live service configuration compatibility remains UNKNOWN until separately verified.
- DL-001 and S11-WX011, original evidence, operating state, and all production data remain unchanged.

## EVIDENCE

- This workstream was registered under user-approved GOV-005 on 2026-10-19.
- GOV-005 registers this workstream only; it does not activate DWS-001 or authorize product, socket, database, or production work.
- 2026-10-19: User explicitly approved shared DWS-001 registration with Governance and Discovery Writer Safety, canonical remote readback, Governance-only closure, then read-only Writer analysis and isolated synthetic socket reproduction. Product and operational changes remain prohibited.
- The user-approved shared DWS-001 registration commit `383d96606f5c727f0cef23eee35fbe06fc37edba` was read back from the canonical remote with matching Governance + Discovery Writer Safety task IDs and required-workstream sets. Governance participation then closed; DWS-001 remains IN_PROGRESS only under discovery-writer-safety, without any product-code, Writer-smoke, Docker or operational changes.

- 2026-10-19: The user asked whether DWS-001 relates to MP4 serialization, was informed DWS is an independent safety blocker surfaced in DL-001 Docker build smoke, and explicitly approved the recommended B option (systemd socket activation) for Writer product implementation and isolated offline testing only. Production service settings, actual socket, runtime/data, Docker build, and deployment remain prohibited. The pre-existing synthetic evidence includes normal kill/restart PASS, pre-unlink replacement FAIL (active pathname removed), and simulated identity collision FAIL; actual inode reuse was not observed in 16 trials. This evidence is not a production incident claim.

## NEXT_DECISION

With the user's separately granted B-option implementation approval, prepare an isolated reviewable systemd socket-activation Writer candidate and offline-only safety tests. Do not modify the canonical production release, run any Docker build, alter CT108 services/sockets, or deploy without new explicit approval.
