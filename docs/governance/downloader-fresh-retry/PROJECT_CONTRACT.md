# Downloader explicit fresh-identity HLS retry API contract

CONTRACT_VERSION: 1.0.0
PROJECT_CONTRACT_STATUS: APPROVED
APPLIES_TO: Only an explicitly requested fresh-ID retry API for failed custom-HLS jobs, preserving prior failed jobs and their source fragments. Initial use is the independently approved DLHLS-001 incident.

## Purpose and narrow routing

- Teddy explicitly approved a small reusable **API-only** action on 2026-11-09 to create a distinct job identity for a failed HLS download while leaving the original failed job, fragments and manifest unchanged. Do not mistake this for approval to resume or rewrite the original.
- Route only design/code/offline tests/deployment of the explicit fresh-ID API through `downloader-fresh-retry / DLFR-001`; this narrow endpoint feature takes precedence over general `downloader / P08LIB-001` solely for these API and admission changes. The normal `/download` duplicate guard, default retry endpoint, generalized downloader engine/queue behavior, Stage9, Writer and Stage11 retain their existing routes.
- The three original jobs and the one guarded live SORA-489 trial remain under `downloader-hls-recovery / DLHLS-001`; this API code task does not authorize an incident trial by itself. Shared cross-domain changes outside this narrow endpoint require separately aligned approval, not silent task-ID reuse.

## Authorized minimal behavior

- Add one authenticated, CSRF-protected explicit action, e.g. `POST /api/tasks/<failed_id>/retry-fresh`, reusing the current application's queue-admission, ownership, capacity/reserve, no-overwrite, source-identity and task-state safeguards. No web UI, HTML/CSS/JS, button or background automation change.
- Accept only a verified persisted failed custom-HLS source record (including protected HLS-plan mismatch), and construct a **new UUID** and separate `.{new_id}.parts` folder using the original saved URL through an existing safe enqueue path. Record a provenance link only on the **new** job; do not mutate, clear, cancel, delete, mark terminal, or reschedule the original task.
- Keep default new-download duplicate protection unchanged. Within this explicit action, refuse active/queued/other-new-ID conflicts, an already-owned title, uncertain original identity, unknown authorization, insufficient space/reserve, or any existing output path. Require one deliberate operator-initiated request; never automatically requeue all failed jobs.
- Preserve existing HLS playlist-plan SHA protection, global single MP4 remux, storage reservations, remote SSH NAS atomic no-overwrite and completed-file publication. Never mix old TS across changed playlist plans or weaken fallback/collision protections.

## Build, verification and release boundaries

- Code/offline tests must be staged in a verified isolated source checkout and validate at minimum: original task/1,395 TS unchanged, new UUID, separate parts and error-only gate, normal duplicate endpoint still 409, ownership/output collision refusal, authenticated+CSRF admission, and no unintended task write on failure. No real download in offline tests.
- A future **single** bounded image build and **Downloader-only** conditional service promotion are approved in principle, but require actual CT108 active/queued/remux idle check and A-method container-only stop held across the full confirmed build; precise disk reserve, image rollback and exact effective Compose parity. Candidate image must preserve the four current operating UI file hashes and include no held P08LIB-001 UI changes. No other service stop/restart or automatic rollback.
- Build/test/registration PASS does not authorize a production network trial. For the three 2026-11-07 incident jobs, `DLHLS-001` separately requires current source/output identity and destination/ownership checks, sufficient required+reserve for download and MP4, no competing worker, and explicit operator GO. Current saved SORA-489 estimate 0 does not establish required size.

## Prohibitions

- No UI promotion, generic queue redesign, old retry semantics change, global duplicate bypass, status spoofing, deletion, TS/manifest editing, NAS/Jellyfin publication by this code task, Docker prune, source-page probe, production download or media-file mutation. Keep original 1,395 fragments and all existing images/backups.
- A failure or unknown result stays BLOCKED. Do not attempt to hide an unresolved new build/incident capacity gap by widening the endpoint or lowering reserve.
