# Workstream routing registry

ROUTER_VERSION: 1.0.0
COMMON_CONTRACT_VERSION: 1.0.1

This file routes a request to its workstream contract and active task. It is not one global task. A PAUSED_FOR_GOVERNANCE or INACTIVE workstream does not pause an independent workstream. INACTIVE means no user-approved task is currently active; it does not remove or reject the workstream's approved design contract. Only registered workstreams are authorized; adding another requires user approval and its own contract and active-work file.

## Routing rules

- Classify work by purpose and by the files/resources it may affect. A repository-root file may belong to a domain workstream; paths alone are not sufficient.
- Select every affected workstream. If work is shared, each selected workstream must show the same authorized task ID and declare the full `REQUIRES_WORKSTREAMS` set.
- A request outside a registered workstream or mismatching any selected task ID fails closed.
- The incident-only `DLHLS-001` route never authorizes generic Downloader source changes, other jobs, runtime deployment or resuming the held `P08LIB-001` UI release.

## WORKSTREAM: governance

STATUS: INACTIVE
TASK_ID: NONE
CONTRACT_PATH: docs/governance/PROJECT_CONTRACT.md
ACTIVE_WORK_PATH: docs/governance/governance/ACTIVE_WORK.md
AREA_HINTS:
- Governance contracts, instructions, routing, validation scripts, and governance CI.
- GOV-001 does not authorize product code changes.

## WORKSTREAM: stage11

STATUS: IN_PROGRESS
TASK_ID: S11-DESIGN001
CONTRACT_PATH: docs/governance/stage11/PROJECT_CONTRACT.md
ACTIVE_WORK_PATH: docs/governance/stage11/ACTIVE_WORK.md
AREA_HINTS:
- Subtitle acquisition, Japanese/audio evidence, ASR, Hermes translation/review, subtitle quality, and Stage11-to-Stage12 subtitle publication.
- Stage11 scripts also live at the repository root; do not route them to generic Downloader work by path alone.

## WORKSTREAM: downloader

STATUS: INACTIVE
TASK_ID: NONE
CONTRACT_PATH: docs/governance/downloader/PROJECT_CONTRACT.md
ACTIVE_WORK_PATH: docs/governance/downloader/ACTIVE_WORK.md
AREA_HINTS:
- General video downloads.
- Download job queues and concurrency control.
- HLS downloads and MP4 remux/conversion.
- Download retries and resume behavior.
- Local storage capacity management.
- NAS final-file transfer and storage.
- Non-subtitle download UI and APIs.
- Non-subtitle Discovery functions except Stage9 Media metadata/NFO/poster/Jellyfin item-state behavior and Discovery Writer Unix socket lifecycle/stale-socket safety, which route to `stage9-media` and `discovery-writer-safety` respectively.
- Other general Downloader functions not assigned to another registered workstream.
- Stage11 subtitle work stays in Stage11 even when its files are at the repository root.
- If another independent workstream is registered later, its contract governs the work assigned to it.
- Classify by purpose and actual affected files/resources; do not route by file location alone.

## WORKSTREAM: downloader-spoofdpi-startup

STATUS: IN_PROGRESS
TASK_ID: DLSPD-001
CONTRACT_PATH: docs/governance/downloader-spoofdpi-startup/PROJECT_CONTRACT.md
ACTIVE_WORK_PATH: docs/governance/downloader-spoofdpi-startup/ACTIVE_WORK.md
AREA_HINTS:
- Only the bundled SpoofDPI helper's noninteractive startup in Downloader, an exact headless argv change, and a bounded single-Downloader-image build and service-only release.
- This specific startup-fix route takes precedence over generic downloader / P08LIB-001 only for the SpoofDPI startup module and this exact candidate release. Existing UI, ordinary download/HLS/queue behavior, DLFR-001 fresh retry API, DLHLS-001 incident trial, DLSS-001 safety, Writer, Stage9 and Stage11 retain their own scopes.
- This task must not enqueue a new video download or retry the three held HLS jobs.

## WORKSTREAM: downloader-hls-recovery

STATUS: IN_PROGRESS
TASK_ID: DLHLS-001
CONTRACT_PATH: docs/governance/downloader-hls-recovery/PROJECT_CONTRACT.md
ACTIVE_WORK_PATH: docs/governance/downloader-hls-recovery/ACTIVE_WORK.md
AREA_HINTS:
- Only the three failed HLS downloads recorded on 2026-11-07 and their one guarded, separate-identity recovery trial.
- This narrow incident route takes precedence over the generic downloader route for those jobs only. All other downloads, generic product code, shared queue changes, UI, Writer, Stage9 and Stage11 remain under existing workstream approval.

## WORKSTREAM: downloader-fresh-retry

STATUS: IN_PROGRESS
TASK_ID: DLFR-001
CONTRACT_PATH: docs/governance/downloader-fresh-retry/PROJECT_CONTRACT.md
ACTIVE_WORK_PATH: docs/governance/downloader-fresh-retry/ACTIVE_WORK.md
AREA_HINTS:
- Only the explicitly requested failed custom-HLS **fresh-ID retry API**, its authenticated admission, duplicate/ownership/capacity checks, and API-only runtime release.
- This narrow endpoint route takes precedence over generic downloader / P08LIB-001 solely for the new fresh-retry API. Ordinary /download and old retry, all other queue/HLS/UI, Writer, Stage9 and Stage11 behavior remain in their existing routes.
- DLHLS-001 owns the three historical failed-job records and any real new-ID trial; this code-registration route does not authorize their download.

## WORKSTREAM: downloader-storage-safety

STATUS: IN_PROGRESS
TASK_ID: DLSS-001
CONTRACT_PATH: docs/governance/downloader-storage-safety/PROJECT_CONTRACT.md
ACTIVE_WORK_PATH: docs/governance/downloader-storage-safety/ACTIVE_WORK.md
AREA_HINTS:
- Only generic shared-filesystem admission safety between Docker image build and Downloader downloads/MP4 remux, with existing space reservations and no-overwrite rules preserved.
- Narrow prevention scope takes precedence over generic downloader routing for the specific build-vs-download disk-contention gate only; it does not reroute ordinary download functionality, the DLHLS-001 three-job recovery, the P08LIB-001 UI, Writer, Stage9 or Stage11.
- Operational build/deploy is conditional on exact image content, competing activity, capacity+reserve, rollback and no unrelated UI promotion.

## WORKSTREAM: discovery-writer-safety

STATUS: INACTIVE
TASK_ID: NONE
CONTRACT_PATH: docs/governance/discovery-writer-safety/PROJECT_CONTRACT.md
ACTIVE_WORK_PATH: docs/governance/discovery-writer-safety/ACTIVE_WORK.md
AREA_HINTS:
- Discovery Writer Unix socket lifecycle, including socket-path preparation and stale-socket cleanup.
- Active socket protection, inode reuse, path-replacement races, process-wide socket lifetime serialization, and forced-termination/restart safety.
- Isolated synthetic tests for the socket lifecycle and its protection boundaries.
- General Discovery database behavior, download processing, MP4 conversion, NAS storage, and Stage11 subtitles remain outside this workstream.

## WORKSTREAM: stage9-media

STATUS: IN_PROGRESS
TASK_ID: STG9MEDIA-001
CONTRACT_PATH: docs/governance/stage9-media/PROJECT_CONTRACT.md
ACTIVE_WORK_PATH: docs/governance/stage9-media/ACTIVE_WORK.md
AREA_HINTS:
- Stage9 media metadata and NFO generation, canonical poster handling, deferred poster completion, and publication state.
- Jellyfin existing-item versus unregistered-item handling and duplicate-notification prevention for Stage9 media.
- Route by purpose and actual affected resources; general downloads, Discovery Writer socket safety, and Stage11 subtitle work remain in their existing workstreams.
- Active task: `STG9MEDIA-001`. `STG9-MEDIA-001` is a historical unapproved proposal and is not the active task ID.
