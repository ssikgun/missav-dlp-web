# Stage9 Media workstream contract

CONTRACT_VERSION: 1.0.0
PROJECT_CONTRACT_STATUS: APPROVED
APPLIES_TO: Stage9 media metadata, NFO/poster lifecycle, publication state, and Jellyfin item-state integration.

This contract approves the Stage9 Media design and safety goals only. It does not authorize product implementation, tests, deployment, runtime changes, or writes to production databases, NAS, or Jellyfin. Each such activity requires a separate active task with explicit user approval.

## Scope and routing

- Own Stage9 metadata handling and NFO/poster generation and publication state, including cases where the canonical poster is unavailable and later becomes available.
- Own the Stage9 Jellyfin boundary for distinguishing an existing registered item from an unregistered item and suppressing duplicate registration notifications.
- Route by purpose and affected resources. General downloads, Discovery Writer Unix socket lifecycle and stale-socket safety, and Stage11 subtitle work remain in their separately registered workstreams.
- A task that changes a shared area must be registered and authorized in every affected workstream. No Stage9 task is currently active.

## Approved design goals and safety policies

- Preserve existing behavior for works with an available canonical poster.
- When no canonical poster is available, generate an NFO from verified, actual metadata. Missing or conflicting required metadata must fail closed; do not fabricate metadata.
- Never generate a fake/placeholder poster or use a video frame as poster art.
- Track NFO completion independently from poster availability/completion. A later canonical poster may complete the poster state without needlessly rewriting a completed NFO or video.
- Preserve collision, ownership, and no-overwrite protections for existing NAS videos and metadata files. Existing NFO, poster, video, or NAS content must not be replaced without explicit scoped authorization. A conflicting existing artifact must remain intact and stop the write path.
- Determine whether a Jellyfin item is already registered before any registration action. Match using verified stable identity/path evidence, avoid creating duplicates, and make notification handling idempotent across retries and repeated job runs.
- Preserve existing Jellyfin path validation; unresolved or invalid library paths must fail closed before any external action.
- Preserve the current retry cap and backoff, title-level lock, and database lock. Stage9 changes must not weaken their ownership, ordering, or failure behavior.
- Use general identity and state-based behavior. Do not add work-number-specific hardcoding, sample-specific exceptions, or temporary bypasses.
- Preserve uncertainty and report offline structural checks separately from operational or user-facing outcomes.

## Task authorization and validation

- This APPROVED contract is a design boundary, not implementation permission. `INACTIVE / NONE` in the Stage9 active-work file means no Stage9 product task is authorized.
- Before implementation, a separate user-approved task must state exact files/candidate, scope, prohibited operations, offline verification matrix, acceptance criteria, and next decision. Production deployment or writes to DB/NAS/Jellyfin require separate explicit authorization in that task.
- Offline acceptance for a future implementation must cover at least: existing canonical poster behavior; NFO creation from actual metadata with no poster; absence of placeholder/video-frame art; later poster completion without NFO/video replacement; collision/no-overwrite preservation; Jellyfin existing/unregistered cases with idempotent notification behavior; retry/backoff and title/database lock boundaries; and generic behavior across multiple identities without per-title logic.
- All offline verification must use isolated temporary files and synthetic/fake integration boundaries. Do not run real downloads, production retries, or write to operational DB, NAS, or Jellyfin as part of offline validation.

## Workstream state

The Stage9 Media design contract remains APPROVED independently of task state. The router and `docs/governance/stage9-media/ACTIVE_WORK.md` must agree on status and task ID. Until a separately approved active task is created, Stage9 remains `INACTIVE / NONE`; the proposed `STG9-MEDIA-001` is not active and authorizes no product work.
