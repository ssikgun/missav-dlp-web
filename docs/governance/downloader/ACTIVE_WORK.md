# Downloader non-subtitle workstream — active work

WORKSTREAM: downloader
TASK_ID: NONE
STATUS: INACTIVE
CONTRACT_VERSION: 1.0.0
REQUIRES_WORKSTREAMS: downloader

## OBJECTIVE

No Downloader implementation task is active. The approved v1.0.0 contract defines the workstream's design and safeguards but does not itself authorize implementation.

## APPROVED_SCOPE

- No product, runtime, operational, deployment, retry, transfer, or data-cleanup task is currently authorized while STATUS is INACTIVE and TASK_ID is NONE.
- The approved contract applies as design and safety guidance to a future separately approved Downloader task.

## PROHIBITED_SCOPE

- Do not treat this registration, the approved contract, or the proposed DL-001 below as authorization to change code or run operational jobs.
- Do not restart containers, retry failed downloads, move/delete files, alter Proxmox or NAS configuration, or change production services.
- Do not modify Stage11 subtitle contracts, state, code, model environments, or artifacts.
- Do not deploy, publish, or write to production systems without a separately approved task that explicitly allows it.

## ACCEPTANCE_CRITERIA

- The approved contract remains v1.0.0 and APPROVED; the router and this file remain INACTIVE / NONE until a task is separately approved and registered.
- Governance preflight must reject implementation requests while this workstream is INACTIVE / NONE.
- Proposed task DL-001 remains inactive unless separately approved and registered with its full scope and checks.

## EVIDENCE

- User approved registering the non-subtitle Downloader workstream and its v1.0.0 contract, including the global one-at-a-time MP4 policy, on 2026-10-17.
- The operational snapshot below was supplied by the user for possible DL-001 planning and was not independently revalidated during GOV-004.

## NEXT_DECISION

After separate user approval and task registration, consider DL-001 — “Downloader storage and MP4 processing reliability.” Proposed goals are: verify configured download concurrency; ensure MP4 conversion runs globally one job at a time; wait safely when storage is insufficient; prevent unnecessary TS fallback after ENOSPC; preserve the existing four failed jobs' fragments; validate MP4 recovery using those fragments; and clean temporary material only after verified NAS final storage.

The supplied incident snapshot says: Proxmox LXC 108 storage was expanded from 64 GB to 100 GB (98 GB filesystem; 34 GB free after expansion); configured `max_concurrent=2` and `auto_retry=True`; the download container is stopped; four jobs failed with ENOSPC; their download segments are present with no missing or zero-byte segments; MP4 recovery has not run; final storage uses `TEDDY_FINAL_BACKEND=ssh`. This snapshot was supplied for planning and has not been independently revalidated here. DL-001 is not active; this file authorizes no retry, recovery, cleanup, service change, or deployment.
