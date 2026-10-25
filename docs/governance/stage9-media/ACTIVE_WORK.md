# Stage9 Media workstream — active work

WORKSTREAM: stage9-media
TASK_ID: STG9MEDIA-001
STATUS: IN_PROGRESS
CONTRACT_VERSION: 1.0.0
REQUIRES_WORKSTREAMS: stage9-media

## OBJECTIVE

Implement safe Stage9 media completion for works without a canonical poster: generate an NFO from verified metadata, track poster completion separately for later supplementation, and avoid duplicate Jellyfin notifications while retaining the existing safeguards.

## APPROVED_SCOPE

- Work only in a new isolated candidate worktree based on the exact approved canonical SHA; do not edit an existing dirty worktree or Stage11 area.
- Inspect and, if required, modify only `teddy_discovery_media_metadata.py`, `teddy_discovery_media_publish.py`, `teddy_discovery_media_pipeline.py`, `teddy_discovery_media_jobs.py`, `teddy_discovery_jellyfin.py`, and the Stage9-specific smoke files needed to verify these changes.
- Preserve normal canonical-poster behavior. For absent or failed poster acquisition, create NFO from verified real metadata where required fields pass validation; track NFO completion, poster state, and failure reason independently.
- Reuse `publish_bundle()` and its SSH atomic-publication boundary where possible. Add a narrowly scoped NFO-only safe path only if existing publication APIs cannot support the approved behavior without weakening protections.
- Preserve file type, symlink, expected-directory, path, ownership, hash, temporary-file, atomicity, and no-overwrite protections. Recognize existing NFO/poster content only when its content hash matches; fail closed on divergence or unsafe filesystem targets. Never alter existing video files.
- Support later canonical-poster completion without needlessly republishing an already completed NFO or video; make partial-publish recovery safe across failure and process restart.
- Review persistence/schema impact before adding or changing state. Do not migrate an operational database. Do not infer new completion state for old jobs or reset existing retry counters without evidence.
- Reuse existing Jellyfin visibility/path validation. Apply `VISIBLE` (skip Created notification), `PENDING` (notify only for a verified path and idempotently), and `ATTENTION` (stop without notification); keep Jellyfin visibility distinct from NFO/poster state.
- Preserve maximum 5 attempts, 3,600-second backoff, 7,200-second stale-running policy, title lock, DB lock, `BEGIN IMMEDIATE`, and restart safety.
- Use only temporary SQLite databases, temporary directories, and fake SSH/NAS/Jellyfin boundaries for product tests. Run the Stage9-specific smoke tests within this isolated offline scope.
- Preserve all unknown operational outcomes as UNKNOWN. Keep any implementation candidate local; no product-source push, merge, or deployment is authorized.

## PROHIBITED_SCOPE

- No production deployment, release change, service or timer change, Docker build, or operation on CT108/CT112.
- No production DB access or write, NAS access or write, Jellyfin access or write, actual download, retry, repair, recovery, or user-data mutation.
- No changes to common or Stage9 contracts, Governance records, Downloader or Discovery Writer Safety `DLDWS-001`, Stage11 `S11-WX011`, or their evidence/artifacts.
- Do not overwrite or replace existing NFO, poster, video, NAS file, or metadata; do not generate a fake/placeholder poster or use a video scene.
- Do not weaken/delete/bypass a safety assertion to make a test pass; do not use per-title hardcoding or temporary title-specific behavior.
- Do not push or merge product source changes. Preserve the candidate as a local reviewable commit only.

## ACCEPTANCE_CRITERIA

- 1. A work with a canonical poster retains existing NFO and poster behavior.
- 2. A work without `cover_url` creates an NFO from validated actual metadata and creates no poster or placeholder image.
- 3. A valid poster URL whose download fails leaves NFO complete and records poster pending/failure independently.
- 4. When a canonical poster becomes available later, only the poster is completed; NFO and video hashes remain unchanged.
- 5. Existing NFO/poster with the same verified hash is safely recognized; different hash, symlink, special file, or unexpected directory fails closed without changing target bytes or video.
- 6. Partial publication failure and process restart are recoverable without duplicate or unsafe publication.
- 7. Jellyfin `VISIBLE`, `PENDING`, and `ATTENTION` produce the approved read/notification behavior; repeated jobs do not duplicate Created notifications, and invalid library/item/video paths fail closed.
- 8. Retry count, 3,600-second backoff, 7,200-second stale-running threshold, title lock, DB lock, `BEGIN IMMEDIATE`, and restart behavior pass offline regression checks without resetting prior counters.
- 9. The same behavior passes for multiple distinct work IDs without per-title branches or hardcoded exceptions.
- 10. All existing Stage9-specific smoke tests and new targeted offline smoke tests pass using only temporary/fake resources; report each count and exact command. No production or operational path is contacted.
- 11. `git diff --check` passes; only the approved Stage9 source and Stage9-specific smoke files change in the implementation candidate; the candidate is committed locally and not pushed or merged.
- 12. Downloader `DLDWS-001`, Stage11 `S11-WX011`, and all operational artifacts remain unchanged.

## EVIDENCE

- User explicitly approved activating `STG9MEDIA-001` and isolated Stage9 product implementation plus offline smoke on 2026-10-25. Approved canonical base and freshly rechecked remote SHA: `5b6a2a68ccc62cca82717cb1655dec983469088e` on `teddy-subtitle-stage11`.
- Stage9 v1.0.0 contract is `APPROVED`; this active task uses only `stage9-media` and does not require a new Governance task or contract change. Governance is independent and currently `INACTIVE / NONE`.
- `STG9-MEDIA-001` was the prior unapproved proposal and is retained as historical context only. The current active ID is the validator-compatible `STG9MEDIA-001`.
- Before activation, all-workstreams structure, Downloader + Discovery Writer Safety `DLDWS-001` preflight, and Stage11 `S11-WX011` preflight passed. Stage9 preflight rejected the task while the route was `INACTIVE / NONE`, as expected.
- Product implementation and test evidence will be appended here after the exact activation commit is read back from the canonical remote. No implementation or product test starts before that readback.

## NEXT_DECISION

After all offline criteria pass, request a separate user approval for any production application. No deployment, operational DB/NAS/Jellyfin access or write, real download, or recovery is authorized by this task.
