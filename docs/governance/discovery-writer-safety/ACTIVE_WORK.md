# Discovery Writer Safety workstream — active work

WORKSTREAM: discovery-writer-safety
TASK_ID: DLDWS-001
STATUS: IN_PROGRESS
CONTRACT_VERSION: 1.0.0
REQUIRES_WORKSTREAMS: governance,downloader,discovery-writer-safety

## OBJECTIVE

Share DLDWS-001 with Downloader to safely investigate the Writer socket smoke failure blocking the DL-001 Docker build candidate, preserving the approved B-option candidate and the distinction between inode reuse and actual socket replacement safety.

## APPROVED_SCOPE

- Read-only review the existing DWS-001 B-option candidate, its isolated smoke evidence, the legacy direct-mode race results, and the DL-001 Writer smoke evidence.
- Preserve the exact B-option candidate and its existing test evidence; do not copy it wholesale into the DL-001 candidate.
- Identify which failures arise from unreliable inode-inequality assumptions and which demonstrate an actual unsafe path replacement or active-socket unlink.
- Propose isolated synthetic offline regression cases that preserve active-listener protection, replacement detection, socket ownership and mode, cleanup boundaries, and restart safety.
- Keep deployment compatibility, cold-start parent-directory ownership, and any other unverified systemd behavior explicitly UNKNOWN.

## PROHIBITED_SCOPE

- This registration execution authorizes no Writer product-code or test changes, no product-specific test execution, and no Docker build. A later execution must explicitly authorize any such work and name its candidate/worktree and validation boundary.
- Do not delete, relax, bypass, skip, or redefine any safety test or turn a reproduced failure into a pass.
- Do not change the existing B-option candidate, DL-001 candidate, live Writer service/socket, systemd units, databases, or operational files.
- No Docker build, download, retry, remux, recovery, NAS/Jellyfin access or change, Stage11 change, or deployment.
- Do not reset, clean, rebase, merge, or force-push.

## ACCEPTANCE_CRITERIA

- Socket inode reuse as a possible filesystem behavior and actual socket-path replacement/unlink safety are assessed and reported separately.
- Prior B-option evidence is retained with its exact candidate SHA; a scoped smoke PASS is never presented as complete production or cross-workstream safety.
- The proposed isolated synthetic matrix retains active listener, replacement-before-unlink, ownership, mode, restart, and no-unlink checks without weakening prior coverage.
- Unverified systemd lifecycle and deployment properties remain UNKNOWN until separately authorized and tested.
- Governance, Downloader, and Discovery Writer Safety registration fields match exactly; Stage11 remains independent and unchanged.

## EVIDENCE

- The complete prior `DWS-001` active record, candidate history, and verification evidence are preserved byte-for-byte in `docs/governance/history/DLDWS-001-registration-base-34dede0/discovery-writer-safety-ACTIVE_WORK.md` (base blob `d1d6316280cac5b87ad3de4a0c4dfacf10298d91`).
- The B-option candidate is `b0831048b3788b9a86a180f040b0152145a079c7`. User-provided isolated runs report syntax, legacy smoke, and socket-activation smoke PASS at that SHA. These are scoped offline results only.
- Direct-mode pre-unlink replacement and simulated identity-collision evidence remain safety FAIL findings. Actual inode reuse was not observed in the recorded trials; its possibility remains distinct from the observed unsafe path replacement.
- Socket-unit static syntax verification passed for the recorded candidate, but full service/socket integration, clean-start directory ownership, and production suitability remain unverified. The Docker build and DL-001 integration remain NOT_RUN.
- Registration preflight at base `34dede0af5bc205ff11af4275727e11627de680b` passed for the existing DWS-001 task.

## NEXT_DECISION

After exact remote registration readback, perform a read-only, SHA-pinned comparison with the DL-001 smoke and produce the cross-workstream failure analysis. Request explicit execution authorization before changing or running Writer tests, product code, or a Docker build candidate.
