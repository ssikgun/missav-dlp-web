# Downloader HLS incident recovery contract

CONTRACT_VERSION: 1.0.0
PROJECT_CONTRACT_STATUS: APPROVED
APPLIES_TO: The three 2026-11-07 failed HLS downloads and one bounded isolated new-identity recovery trial, as approved by Teddy on 2026-11-08.

This is a narrowly scoped, separate workstream that preserves existing P08LIB-001 shared UI approval. The common and Downloader data protection/no-overwrite/fail-closed principles still apply.

## Routing and limits

- Route only the three failed HLS jobs of this incident and one isolated trial here. All other general HLS downloads, shared engine/queue and product code remain in downloader; Writer, Stage9, Stage11 and UI remain separate.
- Any action affecting product code or shared resources outside the bounded trial needs fresh explicit authorization in all affected workstreams; no contract is silently weakened.

## Protection and preconditions

- Preserve original job IDs, URLs, error status, .parts, resume-plan.json, manifests and all 1,395 existing TS fragments, without mixing fragments under a different playlist-plan SHA, deleting backups/caches, overwriting output or reducing the free-space reserve.
- Prefer the zero-TS failed job for a representative new-identity trial; the old retry button cannot be used as a shortcut. Before any network/start/write, verify current no-conflicting-workers/remux, exact source identity/viability, output destination ownership/no-collision, and free >= required + reserve, then record explicit operator go/no-go.
- Treat historic 36.61 GiB free as a dated observation, not trial clearance. A single download test does not prove NAS publication, MP4 finalization or success of the other two jobs.

## Authorization

- This contract and routing authorize only the limited incident work and its bounded read-only preflight; live retries must respect the above safety gate and task authorization. Any new product source, build, deployment, cleanup, NAS/Jellyfin write, shared code or broader retry operation needs separate user approval.
- If job identity, plan SHA, capacity, ownership or another material condition is uncertain, fail closed and preserve the originals.
