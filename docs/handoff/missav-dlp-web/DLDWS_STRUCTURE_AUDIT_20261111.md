# DLDWS-001 — Downloader build-patch and cross-stage interface static audit

REPORT_STATUS: STATIC_SOURCE_MAPPING_COMPLETE_WITH_UNKNOWN
REPORT_TIME: 2026-11-11 08:05:11 KST (Teddy-provided Codex report)
SOURCE_REPO: ssikgun/missav-dlp-web
SOURCE_BRANCH: teddy-subtitle-stage11
SOURCE_SHA: 33d24f6a6fe72c9a47166ab67a18266487a40acf
TASK_ID: DLDWS-001
WORKSTREAMS: downloader,discovery-writer-safety
EVIDENCE_SCOPE: read-only source/Dockerfile; no build or operating-state verification

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
