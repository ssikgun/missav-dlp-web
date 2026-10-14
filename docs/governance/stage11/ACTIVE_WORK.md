# Stage11 subtitle workstream — active work

WORKSTREAM: stage11
TASK_ID: NONE
STATUS: INACTIVE
CONTRACT_VERSION: 1.0.0
REQUIRES_WORKSTREAMS: stage11

## OBJECTIVE

Keep the approved Stage11 subtitle design contract in force while no Stage11 development task is active. INACTIVE means no current user-approved task; it does not mean the design is discarded.

## APPROVED_SCOPE

- Permit read-only contract, source, and evidence inspection.
- Resume Stage11 implementation only after the user approves a separate task with explicit scope and acceptance criteria.

## PROHIBITED_SCOPE

- Do not implement or refactor Stage11/Stage12 subtitle product code while TASK_ID is NONE.
- Do not run Hermes, Whisper, ASR, or any other model for Stage11 without an explicitly approved active task.
- Do not change production queues, databases, services, timers, NAS, Jellyfin, subtitles, or deployments.

## ACCEPTANCE_CRITERIA

- Preflight rejects Stage11 work while this workstream is INACTIVE and TASK_ID is NONE, even though the design contract is APPROVED.
- A future resume requires a user-approved Stage11 task ID, scope, and acceptance criteria.

## EVIDENCE

- The Stage11 contract was formally approved under GOV-002; subtitle product quality remains unresolved.
- P2-N mechanical validation passed for an isolated artifact; P2-O recommended NEEDS_HUMAN_REVIEW and authorized no replacement or publication.

## NEXT_DECISION

The user separately selects and approves the next Stage11 task. GOV-002 does not resume subtitle development.
