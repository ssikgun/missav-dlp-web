# DLDWS-001 — Downloader build-patch and cross-stage interface static audit

REPORT_STATUS: STATIC_AUDIT_COMPLETE_WITH_RUNTIME_UNVERIFIED_AND_P04_PROPOSAL
REPORT_TIME: 2026-11-11 08:05:11 KST (Teddy-provided Codex report)
SOURCE_REPO: ssikgun/missav-dlp-web
SOURCE_BRANCH: teddy-subtitle-stage11
SOURCE_SHA: 33d24f6a6fe72c9a47166ab67a18266487a40acf
TASK_ID: DLDWS-001
WORKSTREAMS: downloader,discovery-writer-safety
EVIDENCE_SCOPE: read-only source/Dockerfile; no build or operating-state verification

## Second duplicate-pair triage — 2026-11-11 09:33:26 KST

GitHub read-only preflight: `b42c17806aaf57222c7e19033ca71dbf7e0928c7`, both `DLDWS-001` paired registrations active; no source/build/deploy writes. Remaining root/final Overlay pairs: app, bootstrap, entrypoint, HTML. Patch write targeting directly from Dockerfile static matrix: app 1 (`teddy_patch_extraction_pause.py`), bootstrap ~10, entrypoint ~6, HTML ~7 plus Dockerfile sed. Direct count is not a measure of hidden semantic risk.

**Conditional next candidate:** app root/Overlay single-sourcing only after addressing the original app-specific extraction-pause patch anchor. Its old pending-pause recovery anchor exists once in old root and zero times in final Overlay. The extraction-pause patch also modifies entrypoint; any possible already-applied branch must keep this latter modification and all checks. Candidate review scope may require `app.py`, `downloader_runtime_overlay/app.py`, and `teddy_patch_extraction_pause.py` (not yet approved). Verify byte-identical final runtime app; existing task safety, MP4 queue, persistent/fresh retry, direct-execution guard; intermediate `teddy_verify_build.py` runtime/final checks, final hash list, and representative API/smoke without production. If equivalence or patch anchors cannot be demonstrated, mark BLOCKED and do not change source.

User prefers batch build after separate candidates, **not** build-per-file; use offline candidate checks and re-run DLSS resource preflight immediately before a future separately approved image build. `REVIEW_ONLY=YES`; `PRODUCT_SOURCE_CHANGED=NO`; `PRODUCTION_CHANGED=NO`; `BUILD=NOT_RUN`; `DEPLOY=NOT_RUN`.

## P04 promotion checkpoint — 2026-11-11 09:21:38 KST

- **GitHub post-push verification (2026-11-11 09:24:07 KST):** Product-source commit `eea42f508ea9c7b8aa349f0725eb9ff04ea40d92` fast-forwarded the selected branch. Independent remote tree/file readback: `HEAD_MATCH=PASS`, `teddy_storage.py` Git blob exactly equals old effective Overlay blob `6634614ed02f3ec58981d3a57ae44d86c2271cb2`, duplicate Overlay storage absent, Dockerfile and final storage hash manifest unchanged, five canonical documents present. GitHub Actions `Project Governance` run `42930979769` **SUCCESS**. **Product source promoted, not built or deployed**; `PRODUCTION_CHANGED=NO`, `BUILD=NOT_RUN`, `DEPLOY=NOT_RUN`.

The separate user-approved GitHub-only source promotion makes root `teddy_storage.py` byte-identical to the previous final Overlay source (`d678abce28a0545d7e9d47633f79cff729c18d7e9436b82c2c31c2921fe914f9`) and deletes **only** repository duplicate `downloader_runtime_overlay/teddy_storage.py`. Exact two-file product scope, approved by Teddy after the bounded offline candidate report; Dockerfile, final hash list, tests, production image and services unchanged. No Docker build/deploy or live NAS/DB write. Earlier synthetic offline checks are narrow evidence; image and runtime behavior, restart, SSH/NAS and cross-filesystem recovery still `UNKNOWN/NOT_RUN`. Paired DLDWS-001 `IN_PROGRESS` retained. Full approval and outcome in both ACTIVE_WORKs and CURRENT_HANDOFF; build requires separate DLSS-001 preflight and user approval.

## Evidence and safeguards

- Codex reported isolated checkout `/tmp/downloader-audit-a2316-1794301122` fast-forwarded and clean at the source SHA; protected original worktree, product source and production unchanged. Common contract v1.0.1 and both DLDWS contracts v1.0.0 remain approved, DLDWS-001 IN_PROGRESS.
- Independent GitHub readback verified the SHA, recursive tracked tree 619 blobs / 424 Python files, 24 root `teddy_patch_*.py` files and exactly 22 direct `RUN python teddy_patch_*.py` Dockerfile invocations. Non-invoked scripts in that Dockerfile: `teddy_patch_mobile.py` and `teddy_patch_proxy_singleflight.py`. Their other usage is not ruled out.
- GitHub source spot checks confirm Stage11-normal feeds current holdings to Stage12 queue, Stage12 batch invokes Stage11 controller while owning rollout/publication, Writer socket supports `health`, `preflight_holding`, `mark_absent`, and completion runner has separately gated media processing. The detailed write-target matrix and remaining interface mapping below are Codex-reported static observations, **not independently rerun**.

## Docker patch write-target matrix (Codex static report)

Aliases: A = `app.py`; B = `teddy_bootstrap.py`; E = `teddy_entrypoint.py`; I = `templates/index.html`. Final `COPY downloader_runtime_overlay/ /app/` replaces A/B/E/I and `teddy_storage.py`. “Overwritten” means intermediate file bytes do not survive unchanged; it does **not** mean the patch or functionality can be removed safely.

| # | Direct Dockerfile patch | Static write target(s) | Effect surviving final Overlay |
|---:|---|---|---|
| 1 | `teddy_patch_vpn_health.py` | E, B, `teddy_network.py` | `teddy_network.py` |
| 2 | `teddy_patch_proxy_pool.py` | `teddy_generic.py`, `teddy_proxy_pool.py` | both (generic may already be patched) |
| 3 | `teddy_patch_proxy_speed.py` | `teddy_proxy_pool.py`, B, `teddy_patch_routing.py`, `templates/teddy-proxy.js` | proxy pool, modified downstream patch, JS |
| 4 | `teddy_patch_task_claim_remux.py` | E, B | overwritten direct targets |
| 5 | `teddy_patch_proxy_learning.py` | `teddy_proxy_pool.py`, E, B, `teddy_patch_routing.py`, `templates/teddy-proxy.js` | proxy pool, modified downstream patch, JS |
| 6 | `teddy_patch_proxy_task_sync.py` | `teddy_proxy_pool.py` | proxy pool |
| 7 | `teddy_patch_proxy_engine_recovery.py` | B | overwritten direct target |
| 8 | `teddy_patch_extraction_pause.py` | A, E | overwritten direct targets |
| 9 | `teddy_patch_hls_transport.py` | E | overwritten direct target |
| 10 | `teddy_patch_hls_pool_clients.py` | E | overwritten direct target |
| 11 | `teddy_patch_hls_transport_bridge.py` | B | overwritten direct target |
| 12 | `teddy_patch_index.py` | I | overwritten direct target |
| 13 | `teddy_patch_logs.py` | I | overwritten direct target |
| 14 | `teddy_patch_storage.py` | I | overwritten direct target |
| 15 | `teddy_patch_routing.py` | I | overwritten, uses previously modified patch script |
| 16 | `teddy_patch_ytdlp_options.py` | I | overwritten direct target |
| 17 | `teddy_patch_browser.py` | I | overwritten direct target |
| 18 | `teddy_patch_split_storage.py` | E, B | overwritten direct targets |
| 19 | `teddy_patch_browser_runtime.py` | B | overwritten direct target |
| 20 | `teddy_patch_auth.py` | B | overwritten direct target |
| 21 | `teddy_patch_downloader_admin.py` | B | overwritten direct target |
| 22 | `teddy_patch_pwa.py` | I, `templates/teddy-icon-180.png` | generated icon survives; I overwritten |

Other effects: Dockerfile direct `sed` commands alter B proxy timing and I stylesheet/script placement before final Overlay; these intermediate bytes are later replaced. Non-invoked `teddy_patch_mobile.py` targets I; non-invoked `teddy_patch_proxy_singleflight.py` targets B and `templates/teddy-network.js`. Some patch source contains runtime code strings with apparent file-writing calls; those are not necessarily build-time writes. Dynamically constructed write paths remain UNKNOWN. Build-time intermediate tests and the preserved non-Overlay files are reasons not to delete patches based on overwrite alone.

## Source build checks and final runtime boundary

- Dockerfile copies root source, applies ordered patches and intermediate checks, then copies final Overlay and verifies a ten-path source SHA manifest, Python syntax and focused file-management/Library/admin smoke. `CMD ["python","teddy_bootstrap.py"]` uses the final Overlay bootstrap. Direct `ENTRYPOINT` is absent.
- Before final Overlay: static declarations for ownership, network, proxy, Discovery/Writer, HLS, intermediate UI and subtitle status tests; `teddy_verify_build.py runtime/final`. After final Overlay: SHA, compilation and targeted UI/admin smoke. These describe declared tests, **not tests run in this audit**, and do not prove final Overlay functional equivalence to intermediate patch outputs.
- Five differing root/Overlay pairs remain A/B/E/`teddy_storage.py`/I, with prior P02 static-only evidence. Existing root-only single-source modules `teddy_generic.py`, `teddy_routing.py`, `teddy_downloader_admin.py` were already consolidated and must not be proposed anew.

## Downloader → Stage9 holding/media boundary (Codex source report)

1. `teddy_discovery_download_api.py` accepts a DVD ID, resolves an approved URL server-side and admits a distinct Downloader task ID after duplicate/ownership checks.
2. Downloader handles HLS/generic work, MP4 queue and verified final storage. Storage/safety errors are not blindly retried as network errors.
3. `teddy_discovery_completion_orchestrator.py` uses final path/size/mtime/DVD ID evidence in `commit_remote_holding` to register a `completion-stage9` holding.
4. `teddy_discovery_completion_runner.py` gates a separate media DB/lock and supports `--skip-media` and `--media-only`; completion is distinct from media processing.
5. `teddy_discovery_media_pipeline.py` validates the held title and publishes metadata/poster/NFO and Jellyfin-facing state under Stage9 ownership.
6. `teddy_library_discovery_writer.py` is the narrow deletion/holding-preflight socket (health, preflight_holding, mark_absent), **not** the general new-download holding writer.
7. Downloader task ID, DVD ID and holding ID are different identities. Individual production task→completion execution linkage remains unverified.

## Stage9 → Stage11 → Stage12 interface boundary (Codex source report)

- `teddy_discovery_stage11_normal_queue.py` reads canonical Discovery holdings and seeds Stage12 inventory/queue, then runs a bounded batch. Despite its filename, the queue/state owner is Stage12. The matching systemd unit/timer files under `deploy/stage11-normal/` do not prove deployed activation.
- `teddy_discovery_stage11_controller.py` returns DVD ID, generated artifact/report paths and hashes; it does **not** own publication. Neither Stage9 poster/NFO/Jellyfin success as an explicit Stage11 prerequisite nor Stage11 failure directly modifying Stage9 completion was found in this static pass; absence is not exhaustively proven.
- `teddy_discovery_stage12_batch.py` calls Stage11 controller and passes results to Stage12 state/publication; `teddy_discovery_stage12_rollout.py` maintains independent per-title state, preserves target identity/no-overwrite, and distinguishes generation, publication, retryable/terminal failures and unresolved states. Jellyfin subtitle recognition is separately checked.
- UI reads Stage12 outcomes through `teddy_subtitle_status.py` and `teddy_library_api.py`. UI state is **not** proof of generation/publication success. Stage11 internals, model/ASR/translation quality and actual subtitles remain outside the selected DLDWS-001 audit scope.
- Future **possible interface extension points only**: canonical holding/DVDid admission, `Stage11ControllerResult` artifact/hash handoff, Stage12 state/transition/publisher, and read-only Library/subtitle status APIs. This authorizes no change.

## Unverified, no implementation authority

- Dynamically built patch targets and complete functional equivalence between intermediate build changes and final Overlay code.
- Current production image/source parity; active timers/services and source-to-runtime execution.
- End-to-end link from individual download task ID to completion/media job and consequences of Stage9 failures across all subtitle entry paths.
- Stage11 ASR/translation quality, actual Stage12 publication/Jellyfin recognition, or runtime retry behavior.
- No new P04 candidate chosen; next deliverable is a risk- and effort-ranked 1–3 candidate plan **without code modification**, followed by Teddy's explicit decision.

RESULT: STATIC_PATCH_MATRIX=REPORTED_COMPLETE; STATIC_INTERFACE_BOUNDARY=REPORTED; RUNTIME_VALIDATION=NOT_RUN; P04_CANDIDATES=NOT_SELECTED; PRODUCT_SOURCE_CHANGED=NO; PRODUCTION_CHANGED=NO; BUILD=NOT_RUN; DEPLOY=NOT_RUN.

## Final structure/risk assessment and proposed P04 order (2026-11-11 08:34:56 KST)

**Status:** final *static assessment* submitted by Codex; no actual image build, live source equivalence, systemd health, download, NAS or subtitle E2E was run. Canonical tree at `c6842e2e0482dda6d54843b7fce2118b1d20bbac`: 620 tracked paths / 424 Python files (independent GitHub tree check; added this audit Markdown after the prior count of 619). A complete per-file runtime-use proof is still unavailable; dynamic import/operational-only candidates remain UNKNOWN.

### Risk/priority ordering

| Group | Static assessment | Proposed treatment |
|---|---|---|
| Root/Overlay `teddy_storage.py` | Final Overlay has additional no-overwrite, SSH remote hash, interrupted publish/recovery protections; no Docker patch directly rewrites that module | **P04 candidate 1: small single-source consolidation**, no behavioral change; medium+ data-safety verification |
| Final Overlay storage smoke gap | Docker's final Overlay phase validates hash/compile and selected UI/admin smoke, not all storage no-clobber behavior | **Conditional candidate 2**: reuse existing bounded synthetic storage collision/preservation check after final Overlay; only if inexpensive and existing coverage inadequate |
| Root/Overlay `app.py`, `teddy_bootstrap.py`, `teddy_entrypoint.py`, `templates/index.html` | Heavy dependencies on patch chain, job safety, HLS/MP4 and UI assets | Defer: no safe small refactor selected on current evidence |
| `teddy_generic.py`, `teddy_routing.py`, `teddy_downloader_admin.py` | Previously consolidated to root single-source | COMPLETE; do not repeat |
| Subtitle interfaces | Stage11 generation and Stage12 state/publication/UI status are separated from Downloader/Stage9 media completion | Preserve ownership; any actual subtitle contract/UI expansion requires its own authorization |

### Candidate 1: minimal byte-preserving storage single source

Proposed product paths: `teddy_storage.py` and `downloader_runtime_overlay/teddy_storage.py` only **if** all static/early-build constraints permit. Goal: root storage bytes match currently effective final Overlay storage and redundant Overlay copy disappears, leaving final image's storage bytes and NAS protections unchanged. Actual Dockerfile/manifest edits are **not assumed unnecessary** until candidate inspection. The Dockerfile's **pre-Overlay** site-key smoke (line 71) and `TEDDY_FINAL_DIR` marker check (line 159) must still pass, as must final Overlay SHA manifest/compile and representative synthetic storage no-clobber/recovery checks. Existing runtime files, NAS media, partial fragments and state remain untouched. New image build/deployment are separately approved, never inferred from static equivalence.

**CHECK_REQUIRED, not proven defect:** `downloader_runtime_overlay/teddy_storage.py` local/mounted crash-recovery branch in `_publish_pending_task_unlocked` accepts a present final destination when source has disappeared. In that branch an SSH-style inline hash comparison is not visible; upper caller and identity evidence may already constrain it. This is not automatically in scope to “fix” during byte-preserving deduplication and is not a claim of observed file corruption.

### Candidate 2: conditional final-Overlay storage validation

Only if the first candidate exposes a meaningful coverage gap, reuse an existing representative storage smoke (one collision+preservation scenario) at the final Overlay stage. Potential source paths are `Dockerfile` and one pre-existing smoke file, exact name to be verified; avoid new test tooling. If existing checks suffice or build cost is disproportionate (GOV-008), defer this option. No code changes approved yet.

### Approval and unknowns

- This report is an **approval request proposal**, not P04 task activation or source/build/deploy authorization. DLDWS-001 remains the currently approved read-only architecture-audit task under Downloader+Writer Safety. If proposed changes touch DLSS-001, Stage9, Stage11, Stage12 or another independently owned resource, obtain separate proper workstream authorization before action.
- Actual production image source, current running systemd/Docker state, all dynamic patch usage, Stage9 task-to-completion mapping and real subtitle publication/Jellyfin recognition remain unverified.
- Next: Teddy selects whether to authorize the smallest byte-preserving P04 source-candidate scope with focused offline checks; then record the exact task approval before any source edit. Builds and production deployments remain separate explicit gates.

## Teddy authorization after audit (2026-11-11 KST)

Teddy answered **"응 승인할께"** to the explicit recommendation to proceed with **isolated source candidate and bounded offline validation only** for candidate 1 (`teddy_storage.py` root plus removal of its identical-behavior Overlay duplicate). This is now recorded under paired `DLDWS-001` ACTIVE_WORK authorization, without changing the common contract, routing or other workstreams. Candidate root contents must be exactly the former final Overlay bytes; inspect Dockerfile's early storage checks (site-key and final-dir marker) and final SHA manifest before doing even the isolated edit. Candidate patch must touch only the two product paths; any manifest/Dockerfile/test/source expansion requires fresh approval. Preserve existing local/SSH no-overwrite/hash/recovery semantics; the potential local recovered-destination hash gap remains CHECK_REQUIRED, not a defect fix authorization. No canonical product promotion, Docker build, operational deployment, NAS/DB/Jellyfin data edit, Stage9/11/12 action, or protected worktree mutation is approved.

Next user gate: review candidate patch plus representative offline results; only afterward decide separate canonical product promotion, build and operating deployment permissions.

## P04 isolated source candidate — Codex result and independent patch review (2026-11-11 09:12:05 KST)

Candidate source HEAD: `b53bb3d41dea156fb05baf25e38151c5ef65756f`; isolated candidate `/tmp/dldws-p04-b53-candidate`. Codex delivered `/tmp/dldws-p04-b53-storage.patch` and `/tmp/dldws-p04-b53-hashes.txt`, supplied as ChatGPT attachments. Uploaded patch SHA-256 independently checked: `c27500b02459612036c90df66fdf219f76102ff90baae9c28a24eb5c241fdae1`; hash-list artifact SHA-256 `f79e80a0540032bcb904eb6ea84341ff5c3f637bbb8851a158bea627c90597ad`.

| Property | Result |
|---|---|
| Exact paths | `M teddy_storage.py`, `D downloader_runtime_overlay/teddy_storage.py` |
| Old root storage SHA-256 | `b45521a8fa8c325787f116be6b4b88cdbc6f708e47d30c35576600382972f74d` |
| Previous Overlay and candidate root SHA-256 | `d678abce28a0545d7e9d47633f79cff729c18d7e9436b82c2c31c2921fe914f9` |
| Manifest storage SHA-256 entry | `d678abce28a0545d7e9d47633f79cff729c18d7e9436b82c2c31c2921fe914f9`, unchanged |
| Git patch structure | 2 paths; Overlay deletion 1,863 lines, root +101/-7 lines |
| Independent patch replay | PASS — unified diff applied **in memory** to canonical GitHub source; candidate root equals previous Overlay byte-for-byte, deleted Overlay has empty result |
| Offline reported checks | syntax/import/site classification (4)/final-dir selection, same-filesystem synthetic collision protection and normal publish, diff-check/reverse patch PASS |
| Unknown | restart recovery, real SSH/NAS, cross-filesystem publish, actual Python 3.10 Docker build, running image and production behavior |

The candidate implements **no intended behavior change**; final Dockerfile source resolution after removal should retain the root storage module, with the original manifest expected hash. This is a source-static result, **not** proof of build/runtime health. The crash-recovery existing-destination branch remains unchanged, with upper-layer identity constraints and hash gap `CHECK_REQUIRED`, not a verified vulnerability.

`CANONICAL_PRODUCT_CHANGED=NO`, `PRODUCTION_CHANGED=NO`, `BUILD=NOT_RUN`, `DEPLOY=NOT_RUN`. Next decision: obtain separate Teddy authorization before any exact two-path GitHub product promotion; image build and operating deployment remain distinct later decisions.
