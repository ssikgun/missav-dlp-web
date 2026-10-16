# Stage11 subtitle workstream — active work

WORKSTREAM: stage11
TASK_ID: GOV-003
STATUS: IN_PROGRESS
CONTRACT_VERSION: 1.0.0
REQUIRES_WORKSTREAMS: governance,stage11

## OBJECTIVE

- Correct only the final Workstream state paragraph in the Stage11 contract so it describes the active-work source of truth and its routing relationship.

## APPROVED_SCOPE

- Register GOV-003 jointly in governance and stage11 for this temporary maintenance task.
- Change only the Stage11 contract's final Workstream state paragraph; preserve its approved design and policies.
- Run the existing governance checks, record evidence, close GOV-003, and restore the pre-existing governance and S11-WX010 states exactly.

## PROHIBITED_SCOPE

- Do not change Stage11 product code, WX010 R6 evidence or experiment files, model settings, or run any model or Smoke.
- Do not change production behavior, the common contract, other workstream contracts, or any Stage11 contract section outside the final Workstream state paragraph.
- Do not change operational services, databases, queues, NAS, Jellyfin, subtitles, or publication state.

## ACCEPTANCE_CRITERIA

- The final Stage11 contract state paragraph points to `docs/governance/stage11/ACTIVE_WORK.md` as the source of the current task ID and status, requires router consistency, explains INACTIVE and BLOCKED without embedding a current task value, and fails closed on mismatch.
- Stage11 `CONTRACT_VERSION: 1.0.0` and `PROJECT_CONTRACT_STATUS: APPROVED` remain unchanged; all design and policy text outside the target paragraph remains unchanged.
- Both selected workstreams register the same GOV-003 task and full `REQUIRES_WORKSTREAMS` set while GOV-003 is active.
- Existing governance structural checks, shared-task authorization check, governance smoke, and `git diff --check` pass.
- The original S11-WX010 active-work document is restored byte-for-byte; final routing is governance `INACTIVE / NONE` and stage11 `BLOCKED / S11-WX010`.
- The closure commit is present on canonical `teddy-subtitle-stage11` and the final remote content is read back and verified.

## EVIDENCE

- Pre-GOV-003 canonical base commit: `d3d1182d4d3ff43d7abe26a6d0ac2eb83423d781`.
- The complete original `docs/governance/stage11/ACTIVE_WORK.md` is preserved by that parent commit (Git blob `84adee78f757baa445bb730aa0601aca58a19af1`; SHA-256 `341ec74adedef6a92704dce4f443513e57e3d095f26f8741b3e83ffd272747fa`). It records `S11-WX010 / BLOCKED`, including the original OBJECTIVE, APPROVED_SCOPE, PROHIBITED_SCOPE, ACCEPTANCE_CRITERIA, EVIDENCE, and NEXT_DECISION.
- S11-WX010 is held only during GOV-003 registration; it is not canceled, completed, replaced, or re-approved. Restore the original bytes and verify both hashes before closure.
- Pre-task router SHA-256: `d4ef54ab47255e9a7bd0e54461b0e97200dde08531ee78e95d3b52c464377728`; pre-task governance ACTIVE_WORK SHA-256: `58f9a108c51bf9f5d67301471bfc4bc6278475998eac71b8484ba4b7563fb2d2`.

## NEXT_DECISION

- Apply and validate the approved minimal paragraph change, close GOV-003, and restore the original governance and S11-WX010 routing state.
