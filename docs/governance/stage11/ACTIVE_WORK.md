# Stage11 subtitle workstream — active work

WORKSTREAM: stage11
TASK_ID: NONE
STATUS: PAUSED_FOR_GOVERNANCE
CONTRACT_VERSION: 1.0.0
REQUIRES_WORKSTREAMS: stage11

## OBJECTIVE

Keep Stage11 subtitle development paused while GOV-001 establishes the workstream governance and the Stage11 contract awaits user approval.

## APPROVED_SCOPE

- Permit read-only contract, source, and evidence inspection only when required by the active governance task.
- Resume Stage11 implementation only after the user approves the Stage11 contract and selects a Stage11 task with explicit scope and acceptance criteria.

## PROHIBITED_SCOPE

- Do not implement or refactor Stage11/Stage12 subtitle product code while this workstream is paused.
- Do not run Hermes, Whisper, ASR, or any other model for Stage11.
- Do not change production queues, databases, services, timers, NAS, Jellyfin, subtitles, or deployments.

## ACCEPTANCE_CRITERIA

- Stage11 preflight rejects work while this workstream remains paused or the Stage11 contract remains unapproved.
- A future resume requires a user-approved Stage11 task ID, scope, and acceptance criteria in this workstream.

## EVIDENCE

- GOV-001 explicitly pauses subtitle development while governance is built.
- P2-O recommends `NEEDS_HUMAN_REVIEW`; it does not authorize a replacement, publication, or new subtitle-development task.

## NEXT_DECISION

The user approves the Stage11 contract and separately chooses the next Stage11 task. GOV-001 completion does not resume subtitle development automatically.
