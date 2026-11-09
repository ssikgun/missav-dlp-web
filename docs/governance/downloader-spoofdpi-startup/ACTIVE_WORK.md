# Downloader SpoofDPI headless startup — active work

WORKSTREAM: downloader-spoofdpi-startup
TASK_ID: DLSPD-001
STATUS: IN_PROGRESS
CONTRACT_VERSION: 1.0.0
REQUIRES_WORKSTREAMS: downloader-spoofdpi-startup

## 2026-11-10 — Teddy authorized narrow headless startup repair and conditional target-only release

- **User decision:** After reviewing why SpoofDPI was absent even though earlier downloads worked, Teddy said `실제 서비스 교체까지 승인할께`, explicitly extending the proposed DLSPD-001 scope from registration/candidate dry-run to **one conditional Downloader-only service promotion**, but no source/network/media retry and no unrelated service operations.
- **Actual CT108 findings:** `spoofdpi 1.5.5 0b49eaf`; `--help` success with `--no-tui` and `--listen-addr`. Docker startup is not health-only, `teddy_bootstrap.py` imports the app, current `teddy_spoofdpi.py` invokes `["spoofdpi"]`, and exactly one startup log event reported `EARLY_EXIT exit_code=1` with sanitized `failed to start tui: could not open a new TTY: open /dev/tty: no such device or address`. Current SpoofDPI process count 0 and 127.0.0.1:8080 closed. The API-only candidate did not overwrite the bundled SpoofDPI startup module.
- **Source delta:** `teddy_spoofdpi.py` argv only to add `--no-tui`, possible matching comment and a small mock test. Separate one-time image-derived overlay candidate; preserve current live DLFR-001 API image `sha256:b31b0b4dd106abf19d3394b5d703391a7ea522151ae61622ec53b6a1c7b2d7a4`, prior image `sha256:ebd164d631450660b79ca29141a3b8c317f71df443b2d209feec51a8a35c000a`, 13 Compose files, existing rollback and UI hash baseline. No full-source image rebuild.
- **Release gate:** Read-only CT108 identity and idle task/remux/process checks; hold admission by stopping only Downloader during its small offline build; verify image-delta-only Compose effective config, Docker space reserve, exact image rollback and no unrelated service change; one target-only recreate after candidate PASS; check process/listener and protected 13 jobs/1,395 TS. No auto-rollback and no media POST.
- **Still blocked independently:** DLHLS-001 SORA-489 source, required total size and fresh NAS/local ownership checks. `RETRY_POST=NOT_RUN`, `DOWNLOAD=NOT_RUN`.

## OBJECTIVE

Restore the configured bundled SpoofDPI localhost HTTP proxy for ordinary future Downloader usage without affecting protected existing content, UI or jobs.

## APPROVED_SCOPE

- Register self-only DLSPD-001 and preserve all other routing task IDs.
- Minimal one-flag startup Python change, representative offline mock/static check, one candidate build from exact current image, and one conditional Downloader-only image promotion with verified rollback and current no-active-work/disk safety.
- Read-only post-deploy localhost listener and startup process health checks. Return to DLHLS-001 for any subsequent video trial.

## PROHIBITED_SCOPE

- No unrelated source, UI, auth, routing, queue, HLS, remux, reserve, NAS/Jellyfin, Writer, Stage9, Stage11, old-job/TS edits, destructive Docker cleanup, dependency recreation or unapproved source-page request.
- No blind Docker restart, held UI promotion or automatic retry/rollback.

## ACCEPTANCE_CRITERIA

- Canonical route, contract v1.0.0 and this current active task pass all-workstream and selected-task governance checks.
- Minimal source argv and offline mock smoke PASS; old source/output/UI/API hashes preserved in a pinned candidate.
- Target-only promotion on preserved Compose/image rollback, network/ports/mounts/other-container parity; current 127.0.0.1:8080 listener and SpoofDPI process healthy; no failed original/TS loss.
- Distinguish registration/source/build/production listener PASS; do not declare actual upstream site or HLS retry success based on proxy listener alone.

## EVIDENCE

- Direct Teddy CT108 outputs on 2026-11-10, official SpoofDPI v1.5.5 docs for `--no-tui`, unchanged current boot file, source/image/runtime observations.

## NEXT_DECISION

Proceed with one focused source candidate and proportional smoke only after this governance registration is verified, then present exact CT108 gated build and rollout steps. Deployment is already approved conditionally; halt on any unknown gate rather than requesting redundant approval. SORA-489 retry remains separately gated.
