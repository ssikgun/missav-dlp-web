# Downloader repository instructions

These shared instructions apply to all work in this repository. Domain-specific design requirements belong in the selected workstream's contract and are not automatically applied to unrelated work.

## Identify the work before acting

1. Confirm `pwd`, `git rev-parse --show-toplevel`, `git branch --show-current`, and the `origin` repository/branch state. Do not assume the current directory or `main` is the project source of truth.
2. Read the common `docs/governance/PROJECT_CONTRACT.md` and the routing registry in `docs/governance/ACTIVE_WORK.md`.
3. Classify the task by both its purpose and the files/resources it may change. Decide whether it is common Downloader work, Stage11 subtitle work, another registered workstream, or shared work across several workstreams. Do not classify by directory alone: Stage11 code also lives at the repository root.
4. Read the contract and `ACTIVE_WORK.md` for every selected workstream. Confirm each contract version, task ID, status, scope, prohibitions, acceptance criteria, and next decision. A shared task must be listed and authorized in every affected workstream.
5. Inspect existing code and evidence before changing anything. Verify whether requested work is already complete so it is not repeated.
6. Read only relevant sections of `docs/handoff/missav-dlp-web/CURRENT_HANDOFF.md` when more history is needed. Handoff history and `NEXT` text cannot override a contract or authorize work.

If a workstream is unregistered, its contract or active-work file is missing, its task ID is not authorized, or selected contracts conflict, stop and report `BLOCKED`. A PAUSED_FOR_GOVERNANCE or INACTIVE workstream blocks work in that workstream only; it does not by itself block an independent workstream with its own approved contract and active task. Unknown or shared scope must not be guessed.

## Shared project rules

- Work only within the selected workstream task(s). Do not add features or change the approved scope.
- Preserve user-approved goals and frozen policies. Do not resolve design conflicts, replace an implementation direction, or change a contract without explicit user approval.
- Production deployment and external writes require explicit authorization in the relevant active task. Do not infer authorization from a past handoff, test, or another workstream.
- Preserve existing ownership, collision, and no-overwrite boundaries for user data, jobs, and published artifacts.
- Do not add one-off or sample-specific exceptions to general product behavior.
- Distinguish implemented behavior from proposed design and unresolved questions. A code or structural-validation PASS is not automatically a product-quality PASS.
- Use an isolated worktree when the authorized task calls for one. Never modify a protected dirty worktree or global Codex instructions unless that exact change is separately authorized.
- Update the existing canonical handoff with important completed state. Keep the routing registry focused on workstream selection; keep each workstream's active file focused on its current task.
