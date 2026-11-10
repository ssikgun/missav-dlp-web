# Downloader HLS incident recovery contract

CONTRACT_VERSION: 1.0.1
PROJECT_CONTRACT_STATUS: APPROVED
APPLIES_TO: The three 2026-11-07 failed HLS downloads: the bounded SORA-489 new-ID trial approved on 2026-11-08 and verified on 2026-11-10, plus one sequential, individually gated new-ID attempt each for FJIN-104 and IPZZ-687 explicitly approved by Teddy on 2026-11-10.

This is a narrowly scoped, separate workstream that preserves existing P08LIB-001 shared UI approval. The common and Downloader data protection/no-overwrite/fail-closed principles still apply.

## Routing and limits

- Route only the three failed HLS jobs of this incident and their specifically approved, separate-identity trials here. The SORA-489 trial is complete; only FJIN-104 and IPZZ-687 remain eligible for one new-ID attempt each, sequentially and after their own safety GO. All other general HLS downloads, shared engine/queue and product code remain in downloader; Writer, Stage9, Stage11 and UI remain separate.
- Any action affecting product code or shared resources outside these bounded trials needs fresh explicit authorization in all affected workstreams; no contract is silently weakened.

## Protection and preconditions

- Preserve original job IDs, URLs, error status, .parts, resume-plan.json, manifests and all 1,395 existing TS fragments, without mixing fragments under a different playlist-plan SHA, deleting backups/caches, overwriting output or reducing the free-space reserve.
- The representative zero-TS SORA-489 new-ID trial passed. For the two remaining jobs (FJIN-104: 1,323 protected TS; IPZZ-687: 72 protected TS), never click the existing same-ID Web UI Retry or bulk retry buttons. Before each live fresh-ID POST, use a bounded read-only gate for the exact failed record/source and title, current source viability, route, no-conflicting-workers/remux, destination ownership/no-collision, and available space >= justified per-item required budget + protected reserve; stop on a material unknown. Record the user's 2026-11-10 approval and the per-item GO evidence. Run one job at a time; verify the new job, original protection and final publication before starting the next.
- Treat historic free-space measurements as dated observations, not clearance for another job. SORA-489 completed and an exact-size MP4 was found in the NAS JAV library; that does not prove source viability, NAS publication, MP4 finalization or success for FJIN-104 or IPZZ-687.

## Authorization

- This contract and routing authorize the bounded incident preflights and, under Teddy's explicit 2026-11-10 approval, at most one distinct new-ID live retry for FJIN-104 followed by one for IPZZ-687, each only after its current safety gate passes. New-job MP4 publication resulting from those two authorized downloads is in scope if ownership/no-overwrite gates pass. Any unrelated source, build, deployment, cleanup, manual NAS/Jellyfin mutation, shared code/UI change, same-ID retry or broader retry operation needs separate user approval.
- If job identity, plan SHA, capacity, ownership or another material condition is uncertain, fail closed and preserve the originals.
