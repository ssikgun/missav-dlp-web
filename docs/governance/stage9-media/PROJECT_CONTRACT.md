# Stage9 Media workstream contract

CONTRACT_VERSION: 1.0.3
PROJECT_CONTRACT_STATUS: APPROVED
APPLIES_TO: Stage9 media metadata, NFO/poster lifecycle, publication state, and Jellyfin item-state integration.

This contract approves the Stage9 Media design and safety goals only. It does not authorize product implementation, tests, deployment, runtime changes, or writes to production databases, NAS, or Jellyfin. Each such activity requires a separate active task with explicit user approval.

## Scope and routing

- Own Stage9 metadata handling and NFO/poster generation and publication state, including cases where the canonical poster is unavailable and later becomes available.
- Own the Stage9 Jellyfin boundary for distinguishing an existing registered item from an unregistered item and suppressing duplicate registration notifications.
- Route by purpose and affected resources. General downloads, Discovery Writer Unix socket lifecycle and stale-socket safety, and Stage11 subtitle work remain in their separately registered workstreams.
- Shared work must be registered and authorized in every affected workstream under the same task ID. The current Stage9 task ID and status are determined by the common routing registry and this workstream's `ACTIVE_WORK.md`; those records must agree.

## Approved design goals and safety policies

- Preserve existing behavior for works with an available canonical poster.
- When no canonical poster is available, generate an NFO from verified, actual metadata. Missing or conflicting required metadata must fail closed; do not fabricate metadata.
- Never generate a fake/placeholder poster or capture a video frame from the downloaded, stored, or streamed work to manufacture art. **Approved 2026-11-03 narrow exception**: a static image already supplied by a verified external work page may be classified and stored as a **thumbnail**, even when its origin may be an excerpt from the work, and displayed as a temporary Jellyfin Primary only as specified in the user-approved fallback policy below. Never mislabel a thumbnail as an authentic official poster.
- Track NFO completion independently from poster availability/completion. A later canonical poster may complete the poster state without needlessly rewriting a completed NFO or video.
- Preserve collision, ownership, and no-overwrite protections for existing NAS videos and metadata files. Existing NFO, poster, video, or NAS content must not be replaced without explicit scoped authorization. A conflicting existing artifact must remain intact and stop the write path.
- Determine whether a Jellyfin item is already registered before any registration action. Match using verified stable identity/path evidence, avoid creating duplicates, and make notification handling idempotent across retries and repeated job runs.
- Preserve existing Jellyfin path validation; unresolved or invalid library paths must fail closed before any external action.
- Preserve the current retry cap and backoff, title-level lock, and database lock. Stage9 changes must not weaken their ownership, ordering, or failure behavior.
- Use general identity and state-based behavior. Do not add work-number-specific hardcoding, sample-specific exceptions, or temporary bypasses.
- Preserve uncertainty and report offline structural checks separately from operational or user-facing outcomes.

## User-approved static-thumbnail fallback design — 2026-11-03

USER DESIGN APPROVAL: if no verified authentic poster exists, use a **site-supplied static thumbnail for the exact DVD-ID** instead of leaving the Jellyfin item without useful representative art, but **do not capture frames locally from video**. Classify images using verified page/URL/source evidence (and format/dimensions as supporting evidence), not aspect ratio alone or guesswork; treat ambiguous identification as unavailable. Preserve true image roles and provenance.

- **Authentic poster first:** retain the existing canonical poster behavior and `poster.<validated-extension>` file convention. Never replace a pre-existing poster or user's own selected art under this design-only approval.
- **Fallback thumbnail second:** only when authentic poster is unavailable and an exact work-page-provided preview has verified provenance, store it separately as `thumb.<validated-extension>` in the correct movie folder. Do not rename a thumbnail to `poster`, claim it is an official poster, create placeholder art, or crop/capture frames from the downloaded film.
- **Jellyfin temporary Primary presentation:** when Jellyfin's ordinary movie-card view would otherwise lack a Primary, the verified external thumbnail may be promoted **in Jellyfin's image state only** as a temporary representative image; keep the NAS file classified as Thumb. Jellyfin does not promise that a `thumb` file alone fills a movie's Primary slot. Only apply to the exact verified movie, and do not override existing manual or non-owned Primary image state. Record the fallback origin/ownership needed for a safe later promotion.
- **Later official poster:** if a verified authentic poster becomes available, safely create the separate `poster.<validated-extension>` only if an approved no-clobber create is possible; retain the existing `thumb` until successful official-poster Primary readback; switch Jellyfin's Primary to authentic poster only if the current image is the exact program-owned temporary fallback, not a user's custom image. After successful readback, the exact program-owned temporary `thumb` may be removed only under the cleanup policy below. Avoid rewriting a completed NFO or any video, replacing an existing poster, or issuing uncontrolled Jellyfin scans/re-notifications.
- **No verified image:** continue the successful NFO-only `PENDING` path. Keep bounded retries, metadata/DVDid identity, network host/redirect/bytes verification, per-title/DB locks, and existing write safeguards.

This is an **approved design-policy amendment, not an implementation or deployment approval**. The specific external site(s) including `missav123.com`, the actual preview endpoint, stable provenance signals, existing Jellyfin Primary ownership handling, and source-specific metadata collection must be verified read-only before a separately approved implementation. Never invent image URLs except for the narrowly approved candidate rule below. Use a Stage9-only integration where feasible; if shared Discovery/Downloader code or Writer resources must change, require matched shared-workstream authorization before edits. Before any runtime write, specify exact affected product files, safe offline tests, one user-approved limited operational canary, and explicit NAS/Jellyfin production write scope in an active task. This new policy supersedes the older blanket prohibition **only** for externally supplied, verified, temporary thumbnail artwork in this section; all other existing Stage9 preservation rules remain in force.

## Approved bounded thumbnail candidate URL exception — 2026-11-03

When an independently verified authentic poster is unavailable, Stage9 may derive only `https://fourhoi.com/<normalized-lowercase-dvd-id>/cover-n.jpg` as a temporary thumbnail candidate. The user accepts that matching an ID in this URL does not prove image content identity or page association; do not claim either or label it an official poster. Require exact HTTPS host and path, no query, fragment, arbitrary port or redirect, existing Gluetun proxy only, bounded response and valid JPEG. Preserve original bytes and create only `thumb.jpg`; failures remain pending/held. Authentic poster takes priority. Preserve all no-overwrite, locking, retry, user-image protection and conditional cleanup requirements. Do not generalize the exception to other domains or paths.

## User-approved temporary-thumbnail cleanup amendment — 2026-11-03

USER DESIGN APPROVAL: Once a verified authentic poster is successfully published and confirmed as the Jellyfin movie's actual Primary, the **exact program-created temporary thumbnail** is no longer required and may be cleaned up. This narrows only the earlier unconditional `thumb` retention requirement; it does not authorize arbitrary deletion or weaken existing user-file protections.

- **Preconditions:** verify exact DVD-ID, movie folder and Jellyfin item/path identity; verified authentic `poster.<validated-extension>` created without clobber and read back; Jellyfin Primary is the confirmed official poster on post-update readback; and the candidate `thumb.<validated-extension>` is an exact recorded program-owned temporary file whose current path, regular-file type, hash and ownership still match. Preserve the existing per-title lock and fail-closed checks. Do not follow symlinks.
- **Allowed cleanup:** delete only that verified program-owned `thumb` after all preconditions hold. Never remove a pre-existing, user-managed, non-owned, changed, or uncertain thumb; never delete an NFO, video, authentic poster, other image, or Jellyfin image entry through this rule.
- **Hold on uncertainty:** if the official poster has not become the confirmed Jellyfin Primary, the user has selected a different Primary, image ownership/identity changed, a concurrent update is suspected, or any check fails, keep the thumb and stop cleanup. An unsuccessful cleanup must not roll back or damage the verified authentic poster; record the pending state and require full revalidation before a later cleanup attempt.
- **Jellyfin safety limitation retained:** Jellyfin 10.11.11's inspected image setter does not provide atomic conditional replacement. This cleanup amendment **does not** waive the prohibition on overriding manually selected/non-owned Primary images or approve a best-effort race exposure. The safe automatic Primary-switch method or a separate explicit user risk-policy choice remains unresolved.

This is **design/contract approval only**. It does not itself authorize product code edits, NAS file deletion, Jellyfin image writes, production deployment or retroactive cleanup. Such actions require exact scope and explicit production-write/delete authorization in the active Stage9 task. Offline acceptance must include successful owned-thumb cleanup after confirmed official-Primary readback, and retained thumbs for unowned/changed files, unconfirmed Jellyfin Primary, errors, and manual-image changes.

## Task authorization and validation

- This APPROVED contract is a design boundary, not implementation permission. `INACTIVE / NONE` in the Stage9 active-work file means no Stage9 product task is authorized.
- Before implementation, a separate user-approved task must state exact files/candidate, scope, prohibited operations, offline verification matrix, acceptance criteria, and next decision. Production deployment or writes to DB/NAS/Jellyfin require separate explicit authorization in that task.
- Offline acceptance for a future implementation must cover at least: existing canonical poster behavior; NFO creation from actual metadata with no poster; absence of placeholder/video-frame art; later poster completion without NFO/video replacement; ownership-verified temporary-thumb cleanup only after confirmed official-Primary readback; collision/no-overwrite preservation; Jellyfin existing/unregistered cases with idempotent notification behavior; retry/backoff and title/database lock boundaries; and generic behavior across multiple identities without per-title logic.
- All offline verification must use isolated temporary files and synthetic/fake integration boundaries. Do not run real downloads, production retries, or write to operational DB, NAS, or Jellyfin as part of offline validation.

## Workstream state

The Stage9 Media design contract approves only Stage9 design goals and safety policies. The current task ID and status are determined by the common routing registry and `docs/governance/stage9-media/ACTIVE_WORK.md`; those records must agree. `INACTIVE / NONE` means no Stage9 product task is authorized. The current approved task ID is `STG9MEDIA-001`; `STG9-MEDIA-001` remains a historical unapproved proposal. Production deployment, operational database writes, and NAS/Jellyfin writes require separate explicit approval.
