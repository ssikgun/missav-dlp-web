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
- One-time read-only deployment preflight approved by the user on 2026-10-25: only after this exact authorization record is committed and read back from canonical `teddy-subtitle-stage11`, inspect CT108/CT112 Stage9 release and service/container/runtime metadata, Stage9 DB schema and required aggregate state, identified Stage9 NAS video/NFO/poster path metadata and small-sidecar hashes, and Jellyfin library/item visibility using required GET requests. DB access is limited to a SQLite read-only URI with `PRAGMA query_only=ON` and `SELECT`/`PRAGMA`; NAS access is limited to the identified Stage9 paths; Jellyfin is GET-only. Do not execute a Python runner, job, download, retry, scan, or recovery. This one-time preflight does not authorize deployment, migration, service changes, or any write.
- Separate one-time post-event read-only review approved by the user on 2026-10-25, effective only after this authorization record is committed and read back from canonical `teddy-subtitle-stage11`: inspect the Stage9 service/timer state and bounded existing journald records for 2026-10-25 10:10–10:20 KST; inspect metadata only for `.py` and `.pyc` files in the reverified active release; query only the minimum Stage9 media-job state through a SQLite `mode=ro` URI with `PRAGMA query_only=ON` if opening the DB is safe; and inspect existence, location, mtime, and size of existing backups of the Stage9 media DB. Do not import Python runtime modules. This is a post-event cause review only and authorizes no runtime or data changes.

## PROHIBITED_SCOPE

- No production deployment, release change, service or timer change, Docker build, Python runner/job execution, or mutable operation on CT108/CT112. CT108/CT112 reads are allowed only within the separately recorded deployment preflight or post-event review, and only after that authorization record is committed and read back.
- No production DB mutation. Read-only DB queries are limited to the specific SQLite/`query_only` scopes in the two recorded one-time reviews above. No NAS write; NAS reads are limited to the identified Stage9 sidecar path in the deployment preflight. No Jellyfin write; GET-only access is limited to the deployment preflight.
- The post-event review does not authorize Python cache deletion, regeneration, touch, permission/ownership changes, compilation, service/timer actions, runner/job execution, DB writes or migration, backup creation/restoration, NAS or Jellyfin operations, recovery, or deployment.
- No changes to common or Stage9 contracts, the common router, other Governance records, Downloader or Discovery Writer Safety `DLDWS-001`, Stage11 `S11-WX011`, or their evidence/artifacts. This approval authorizes only the additional scope and evidence/next-decision update in this Stage9 active-work file; it does not create a Governance workstream task or authorize a broader policy change.
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
- On 2026-10-25 the user separately approved one read-only Stage9 deployment preflight. At authorization-record preparation, `origin/teddy-subtitle-stage11` was rechecked at `08f012f8fcc398d2a31d7c971240fe40aced929a`. This exception is effective only after the approval-record commit is pushed fast-forward and its exact content is read back; no operational access is authorized before then. It does not authorize a product-code change, deployment, operational migration, or write. Append the preflight evidence and remaining risks here after inspection.
- On 2026-10-25 the user approved a separate one-time post-event read-only review of the Stage9 timer run observed at 10:14:50 KST, possible active-release Python cache change, and Stage9 media DB backup readiness. Canonical base SHA for this authorization is `ecc6fcf9c0878f064bca98cf2dc8f36ac1be463a`; this record must be committed and exactly read back before operational inspection. This authorization does not permit cache cleanup, service or timer changes, DB changes, NAS/Jellyfin writes, recovery, or deployment.

## NEXT_DECISION

After the one-time read-only preflight, append its findings and request separate user approval before any production deployment, DB migration/write, service change, NAS publication, Jellyfin mutation, real download, retry, or recovery.

After the separate post-event review, append its findings and remaining risks. Any cache cleanup, service/timer action, DB migration/write, NAS/Jellyfin mutation, recovery, or deployment still requires separate explicit user approval.
