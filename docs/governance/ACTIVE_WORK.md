# Workstream routing registry

ROUTER_VERSION: 1.0.0
COMMON_CONTRACT_VERSION: 1.0.0

This file routes a request to its workstream contract and active task. It is not one global task. A PAUSED_FOR_GOVERNANCE or INACTIVE workstream does not pause an independent workstream. INACTIVE means no user-approved task is currently active; it does not remove or reject the workstream's approved design contract. Only registered workstreams are authorized; adding another requires user approval and its own contract and active-work file.

## Routing rules

- Classify work by purpose and by the files/resources it may affect. A repository-root file may belong to a domain workstream; paths alone are not sufficient.
- Select every affected workstream. If work is shared, each selected workstream must show the same authorized task ID and declare the full `REQUIRES_WORKSTREAMS` set.
- A request outside a registered workstream or mismatching any selected task ID fails closed.

## WORKSTREAM: governance

STATUS: IN_PROGRESS
TASK_ID: GOV-004
CONTRACT_PATH: docs/governance/PROJECT_CONTRACT.md
ACTIVE_WORK_PATH: docs/governance/governance/ACTIVE_WORK.md
AREA_HINTS:
- Governance contracts, instructions, routing, validation scripts, and governance CI.
- GOV-001 does not authorize product code changes.

## WORKSTREAM: stage11

STATUS: IN_PROGRESS
TASK_ID: S11-WX011
CONTRACT_PATH: docs/governance/stage11/PROJECT_CONTRACT.md
ACTIVE_WORK_PATH: docs/governance/stage11/ACTIVE_WORK.md
AREA_HINTS:
- Subtitle acquisition, Japanese/audio evidence, ASR, Hermes translation/review, subtitle quality, and Stage11-to-Stage12 subtitle publication.
- Stage11 scripts also live at the repository root; do not route them to generic Downloader work by path alone.
