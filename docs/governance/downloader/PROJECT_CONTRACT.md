# Downloader non-subtitle workstream contract

CONTRACT_VERSION: 1.0.0
PROJECT_CONTRACT_STATUS: APPROVED
APPLIES_TO: General Downloader functions outside subtitle work and outside any other separately registered workstream.

This approved contract defines design goals and safeguards for non-subtitle Downloader work. Contract approval does not authorize implementation, operational changes, deployment, external writes, or data cleanup; those require an active, task-specific approval.

## Scope and routing

This workstream is intended for general video download behavior, download queues and concurrency, HLS and MP4 remuxing, retry/resume, local temporary storage, final storage and transfer, download status/settings UI and APIs, and non-subtitle Discovery functions.

Classify work by its purpose and actual affected files and resources. A file being at the repository root does not make Stage11 subtitle work part of this workstream. If a new independent workstream is registered later, its contract governs the work assigned to it. Shared changes require the same task ID and complete required-workstream set to be registered and authorized in every affected workstream.

## User data protection

- Preserve in-progress downloads, segments, resume state, and job history.
- Do not overwrite completed files or change/delete NAS files without explicit authorization in the selected task.
- Keep ownership, collision, and no-overwrite protections intact unless the user explicitly approves a scoped change.
- Do not remove temporary or partial files until the task's approved validation proves they are safe to remove.

## Download reliability

- Make configured download concurrency match actual execution behavior and prevent unexpected duplicate jobs.
- Track failure reasons, retry state, and resumable progress so a failed job can be diagnosed and continued safely.
- On resource or storage shortage, wait or stop safely with a traceable reason; do not start work that can corrupt or needlessly duplicate existing data.
- Preserve recoverable partial downloads and their segment state across failures.

## MP4 processing and storage

- Treat download concurrency and MP4 remux/conversion concurrency as separate controls.
- MP4 remux/conversion must execute globally one job at a time, independently of configured download concurrency. Any change to this policy requires explicit user approval.
- Distinguish a successful remux/conversion from verified final storage.
- Retain temporary source material until the approved final-storage verification succeeds.
- On ENOSPC or another storage failure, avoid producing redundant outputs that increase storage pressure; retain the source fragments needed for recovery.
- Any NAS write, transfer, cleanup, or deletion requires explicit authorization in the selected task and must preserve existing ownership and collision protections.

## Task authorization and safety

- Every change requires an approved task ID with explicit scope, prohibited scope, acceptance criteria, evidence, and next decision in this workstream's ACTIVE_WORK file.
- INACTIVE / NONE means there is no active implementation authorization. A proposed task ID in a draft or handoff is not authorization.
- Keep code/structural validation results separate from operational and user-facing product results.
- Deployment, production service changes, external writes, retries of production jobs, and data cleanup require separate explicit authorization in the relevant task.
- Do not bypass or modify Stage11 subtitle contracts, data, model environments, artifacts, or publication protections.

## Existing design and implementation

- Inspect the current runtime and verified existing implementation before proposing changes; do not recreate an already working feature unnecessarily.
- Preserve existing normal behavior and user-approved design. Do not introduce broader architecture or change behavior beyond the approved task.
- Treat incident notes and observed metrics as evidence to verify, not proof that a particular implementation change is required.
- This contract candidate makes no claim that any listed policy is implemented or that the current product meets it.

## Approval state

This contract is APPROVED as the design and safety policy for its scope. It does not authorize a product task by itself. The current task ID and status are recorded in `docs/governance/downloader/ACTIVE_WORK.md` and must match the Downloader entry in the routing registry. INACTIVE / NONE means no Downloader implementation task is authorized. Any change to the globally serialized MP4 policy requires explicit user approval.
