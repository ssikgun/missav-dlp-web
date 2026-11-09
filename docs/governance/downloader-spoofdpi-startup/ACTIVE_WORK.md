# Downloader SpoofDPI headless startup — active work

## 2026-11-10 — DLSPD-001 CT108 read-only deployment capacity/data baseline PASS (NO STOP)

- **Teddy direct CT108 result:** hostname `downloader`, current container ID `62ddcadf45be7a72f121c71802ddc10ada0beab849b7582568d2bee92147099c`, live image `sha256:b31b0b4dd106abf19d3394b5d703391a7ea522151ae61622ec53b6a1c7b2d7a4`, old original image `sha256:ebd164d631450660b79ca29141a3b8c317f71df443b2d209feec51a8a35c000a` both available. All 13 tasks unchanged (10 complete, 3 failed, 0 busy), failed parts count 0+72+1323 = 1,395; running `/app/teddy_spoofdpi.py` SHA256 `ba0a04d5ef952a1b388242154d50daf857a1347508ae39633292c6291d8534ac` matches current pre-fix source.
- **Rollback and storage:** `/opt/missav-dlp-web/backups/dlfr001-api-release-b31b0b4d/rollback-manifest.json` present; free `41004101632` B (~38.2 GiB), reserve `5254478438` B and one-build budget `8589934592` B passed. Four containers running: `missav-dlp-web`, `gluetun-missav` healthy, `missav-vpn-browser-selkies`, `missav-vpn-browser-mobile-selkies`; their reported short IDs are 62ddcadf45be, 8a66f78e5ff0, c4863d2f00e9, 6c79fd989f56. This is a time-bound snapshot only.
- **Next:** extract one pinned committed source file to a new isolated private staging directory while current Downloader remains running, verify file SHA256 and provenance; then recheck latest live workers/FFmpeg and stop only Downloader for the offline image build, preserving other container identities and the full rollback. `READ_ONLY_PREFLIGHT=PASS`, `DOWNLOADER_STOP=NOT_RUN`, `IMAGE_BUILD=NOT_RUN`, `DEPLOY=NOT_RUN`, `DOWNLOAD=NOT_RUN`.

## 2026-11-10 — DLSPD-001 governance CI PASS and one-file headless source candidate committed (NO BUILD)

- **Registration:** atomic governance-only commit `c3c41995af3ac36526f06e246eb8c53f01f3f062` added this narrow route, approved v1.0.0 contract, active task and governance checkpoint. GitHub Actions `Project Governance` run `42719743215` completed `success`, including `Validate governance metadata and scope` and `Run offline governance smoke checks`. Existing routes/P08 UI hold preserved.
- **Code-only commit:** `ca2e5236636d72884241d604df207c256182b3b3` updated exactly `teddy_spoofdpi.py`: `popen(["spoofdpi"], ...)` -> `popen(["spoofdpi", "--no-tui"], ...)`, plus matching docstring. GitHub source readback exact candidate match, new Git blob `afdbae9fb569507973c286a8c34983834a79b7a0` and local Python file SHA256 `4c47ddafe6dcb7c478a47ac711c7c3ef7afcad0cde6c6e176d5a49ac30a1792b`; one-line source delta, `+13` bytes.
- **Offline checks:** `python3 -m py_compile` PASS and two mocked startup paths `START_ALIVE HEADLESS_ARGV` and `EARLY_EXIT HEADLESS_ARGV` PASS with preserved `stdout=PIPE`, `stderr=STDOUT`, and startup diagnostics. No real SpoofDPI instance or network test; `SOURCE_SMOKE=PASS`, `EXTERNAL_NETWORK=NOT_RUN`, `DOCKER_IMAGE_BUILD=NOT_RUN`, `DEPLOY=NOT_RUN`, `DOWNLOAD=NOT_RUN`.
- **Next:** CT108 fresh read-only no-active-download/remux, full 13-job protected baseline, space reserve/build headroom, Gluetun/Selkies identity, no competing builder and current DLFR image check; then only if PASS stop just Downloader and extract pinned `teddy_spoofdpi.py` to an isolated build context without modifying the protected dirty checkout. One offline image-derived candidate and image-only Docker Compose promotion on confirmed parity. No SORA-489 POST.

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
