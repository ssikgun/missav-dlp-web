# Downloader common project contract

CONTRACT_VERSION: 1.0.0
PROJECT_CONTRACT_STATUS: DRAFT_PENDING_USER_APPROVAL
APPLIES_TO: all registered workstreams in ssikgun/missav-dlp-web

This is a common-policy review candidate created under the one-time GOV-001 bootstrap authorization. It remains a draft pending user approval. Domain-specific product goals and safeguards live in the selected workstream contract; this document does not make one workstream's rules global to unrelated work.

## Shared project baseline — DOCUMENTED_BASELINE

The repository README describes a browser-based MissAV downloader: a user submits a URL, video download runs in the background and saves MP4 output, and jobs can resume/retry. This is project context, not authorization to change product behavior. Details for Discovery, UI, subtitle generation, operations, or other areas require their own registered workstream contract and active task.

## Common goals and policies — DRAFT_PENDING_USER_APPROVAL

- Preserve user-approved product goals for each workstream. Do not reinterpret one domain's goal as the goal of the entire Downloader project.
- Keep existing user data, job state, source material, and published outputs safe and traceable.
- Preserve existing ownership, collision, and no-overwrite boundaries unless the user approves a change through the affected workstream contract.
- Make work fail closed when identity, ownership, evidence, scope, or authorization is missing or inconsistent.
- Reuse verified implementations and avoid one-off exceptions in general behavior.
- Treat code/test success as evidence for the tested technical property only; assess each workstream's product goals separately.
- Do not deploy, publish, delete, replace, mutate production data, or write to external systems unless the selected task explicitly authorizes that action.
- Do not change the common contract or a workstream contract without explicit user approval.

## Workstream isolation

`docs/governance/ACTIVE_WORK.md` is the routing registry, not one global task that every area must obey. Each registered workstream points to its own contract and active-work file. A paused task pauses only its workstream. Independent work may proceed only when that workstream is registered, its contract is approved, and its own task is active and authorized.

Select every workstream affected by the task's purpose and actual files/resources. Shared work requires the same task ID to be active in every affected workstream, and preflight must verify every selected contract. An unregistered workstream or missing task authorization fails closed. The registry is not permission to create new workstreams; user approval is required to register one.

If common and domain-specific policies conflict, stop and report the conflict for user decision. Do not infer which contract should be weakened or take precedence.

## Approval state

This draft records common governance only. Until the user approves it, it is a review candidate and must not be represented as a final project policy. Its status or version changes only through a user-approved governance task.
