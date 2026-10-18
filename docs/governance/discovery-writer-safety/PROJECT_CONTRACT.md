# Discovery Writer Safety workstream contract

CONTRACT_VERSION: 1.0.0
PROJECT_CONTRACT_STATUS: APPROVED
APPLIES_TO: Discovery Writer Unix socket lifecycle and its safety validation only

This contract covers the Unix socket lifecycle used by the Discovery Writer. It is separate from general non-subtitle Discovery work, which remains in the Downloader workstream unless assigned to another registered workstream.

## Scope and routing

- Manage Writer socket startup and shutdown lifecycle.
- Identify and safely clean stale socket paths.
- Protect active listeners against unlink, inode reuse, and path-replacement races.
- Review process-interoperable socket-lifetime serialization and forced-termination/restart behavior.
- Validate the scoped safety properties in isolated environments using synthetic sockets and test data.
- Route by purpose and actual affected resources, not by file location alone. A source file containing both socket lifecycle and general Discovery database operations is in this workstream only for its socket-safety changes.

General Discovery database behavior, download processing, MP4 conversion, NAS storage, and Stage11 subtitle work are outside this workstream.

## Safety goals

- Never remove a socket path while an active listener owns it.
- Fail closed when liveness, ownership, path identity, or safe cleanup cannot be established.
- Do not rely on inode inequality as proof that a socket path has been replaced safely; inode values may be reused.
- Coordinate supported Writer processes so concurrent startup and cleanup cannot remove an active listener.
- Preserve parent-directory, ownership, permissions, and existing database/restart protections.
- Keep verification isolated from production sockets, services, databases, and user data unless a separate active task explicitly authorizes a specific operation.

These are approved design and safety goals; they do not claim the current implementation satisfies them.

## Task authorization and acceptance

- Every implementation or test task requires a user-approved task ID recorded in this workstream's `ACTIVE_WORK.md` and matching the routing registry.
- `INACTIVE / NONE` means no Writer Safety task is authorized. DWS-001 is a proposed future task and is not active under this contract registration.
- Each task must state its precise allowed and prohibited scope, evidence, acceptance criteria, and next decision.
- Completion requires the task's approved synthetic race cases and existing safety protections to pass. Unverified cases remain UNKNOWN; a test pass is not production verification.
- Production service changes, socket removal/replacement, database writes, Docker build/deployment, and changes to unrelated Downloader or Stage11 behavior require separate explicit authorization in the affected workstream task.
