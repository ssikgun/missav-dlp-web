# Downloader SpoofDPI headless startup — active work

## 2026-11-10 — DLSPD-001 production Downloader-only promotion and SpoofDPI listener PASS

- **Teddy's exact CT108 apply output:** Previous stopped Downloader identity/rollback, three other running container states, disk reserve and image-only 14-file Compose rendering all PASS. `docker compose up --detach --no-deps --no-build --pull never --force-recreate --wait` on **only** `missav-dlp-web` returned `COMPOSE_UP_EXIT_CODE=0`, `COMPOSE_UP=PASS`, `DEPLOY_APPLY=PASS`.
- **New runtime:** Container ID `f3df7dc330aa85d6395e269e0d723b1ae47515344f4c3b9ab399042cdb1f2158` is running pinned candidate ID `sha256:7f115859edaa5eb9bd657f74c60741db5ac9d66fdb9667982e67bc7a0a95676f`; original 13 Compose inputs + new override label chain PASS. Old vs new user/command/entrypoint/env, network/ports/restart/group/privilege/read-only settings and mount signatures PASS; all three Gluetun/Selkies container IDs and running state unchanged; previous image `sha256:b31b0b4dd106abf19d3394b5d703391a7ea522151ae61622ec53b6a1c7b2d7a4` still preserved. Rollback paths and SHA recorded at preceding checkpoint.
- **Post-deploy read-only in-container check:** 13 original tasks = 10 completed + 3 protected errors + 0 busy; 1,395 protected TS unchanged. `SPOOFDPI_PROCESS_COUNT=1` and `SPOOFDPI_LISTENER=OPEN` (127.0.0.1:8080), `SPOOFDPI_RUNTIME=PASS`, `PROTECTED_DATA=PASS`; `DLSPD001_DEPLOY=PASS`, `DOWNLOADER=RUNNING`.
- **Explicit boundary:** This proves local headless startup and listener, **not** source-site reachability, master playlist viability, complete HLS byte budget or any successful download. `DOWNLOAD_TEST=NOT_RUN`, `RETRY_POST=NOT_RUN`. The separate `DLHLS-001` SORA-489 incident trial remains gated and must not be posted until its own source/size/ownership/worker checks PASS. No held UI P08 promotion. Keep existing old image and rollback; no automatic cleanup.

## 2026-11-10 — DLSPD-001 targeted Compose promotion preflight PASS (NO DEPLOY)

- **Teddy CT108 directly verified:** Current Downloader stays stopped on old API image ID `sha256:b31b0b4dd106abf19d3394b5d703391a7ea522151ae61622ec53b6a1c7b2d7a4`, old tag and new headless image `sha256:7f115859edaa5eb9bd657f74c60741db5ac9d66fdb9667982e67bc7a0a95676f` identities PASS. Exactly 13 original Compose paths + prior DLFR image override (14th) validated; prior override byte SHA256 `501344b65d7a36c0d3f180eeec2e406242519b94afbd55946584f8f97b890027` PASS.
- **Private release assets staged:** New isolated image-only override `/opt/missav-dlp-web/backups/dlspd001-headless-tAZ957uv/compose-image-only.yml` SHA256 `70196a4223be7d9215c5d12c916177076413c2ef015595c052142219bf07d547`; rollback manifest `/opt/missav-dlp-web/backups/dlspd001-headless-tAZ957uv/dlspd001-rollback-manifest.json` PASS. Original previous release override and source unchanged. Rendered original 13 files + old override against original 13 + new override: `COMPOSE_RENDER=PASS`, `IMAGE_ONLY_DIFFERENCE=PASS` with full effective Compose JSON equal after normalizing the one service image tag. Free `41002983424` B, reserve `5254478438` B: `DISK_RESERVE=PASS`.
- **Stage final status:** `DEPLOY_PREFLIGHT=PASS`, `OLD_CONTAINER=STILL_STOPPED`, `DEPLOY=NOT_RUN`, `DOWNLOAD=NOT_RUN`. Target-only service promotion has Teddy's explicit prior approval under DLSPD-001, but is not yet executed. Next fresh before/after identity checks, `docker compose up --no-deps --no-build --pull never` only service with pinned candidate; after deployment verify status, process and localhost proxy listener, 13 tasks/1,395 TS, other service identities, previous image rollback. No SORA-489 live retry.

## 2026-11-10 — DLSPD-001 Compose label chain corrected: 13 base + 1 DLFR override (NO DEPLOY)

- **Teddy direct CT108 diagnostic:** A preliminary private override staging script stopped before writing at the incorrect `len(config_files)==13` assertion. The stopped **current** DLFR-origin container has project/service `missav-dlp-web`, working directory `/opt/missav-dlp-web` and **14** original Compose label paths. All 14 paths are regular, non-symlink valid files. Files 1–13 are preserved preexisting Compose inputs; file 14 is exactly `/opt/missav-dlp-web/backups/dlfr001-api-release-b31b0b4d/compose-image-only.yml`, and is last in the chain. Both proposed DLSPD `compose-image-only.yml` and `dlspd001-rollback-manifest.json` remained absent; `OLD_CONTAINER=STILL_STOPPED`, `DEPLOY=NOT_RUN`, `DOWNLOAD=NOT_RUN`.
- **Corrected next step:** Derive the old effective Compose rendering from all labeled 14 files; stage a private new override by replacing only the exact old DLFR image tag in the verified 14th override; derive proposed rendering from files 1–13 plus the staged replacement override. Require structurally identical JSON config except the one service's image field, and record explicit old 14-file rollback chain/image identity. Keep current Downloader stopped until fresh all-pass, then separately apply one approved targeted service-only cutover; no media retries.

## 2026-11-10 — DLSPD-001 CT108 candidate image/UI/runtime parity PASS (NO DEPLOY)

- **Teddy CT108 direct verification:** Original Downloader container remains stopped on image `sha256:b31b0b4dd106abf19d3394b5d703391a7ea522151ae61622ec53b6a1c7b2d7a4`; exact new candidate tag `dlspd001-headless-candidate:20261110` resolves to `sha256:7f115859edaa5eb9bd657f74c60741db5ac9d66fdb9667982e67bc7a0a95676f`. `OLD_CONTAINER=PASS`, `CANDIDATE_IDENTITY=PASS`.
- **Strict image preservation:** Old vs candidate Docker image runtime config fields `User, Env, WorkingDir, Entrypoint, Cmd, ExposedPorts, Volumes, Healthcheck, StopSignal, Shell, Labels` returned `CONFIG_DIFFERENCES=[]`, `RUNTIME_CONFIG=PASS`. An isolated non-network read-only, least-privileged `docker run --entrypoint python` verified exact SHA-256 of `app.py`, `teddy_entrypoint.py`, `teddy_downloader_admin.py`, all four protected HTML/CSS/JS files and only changed `teddy_spoofdpi.py` (digest `4c47ddafe6dcb7c478a47ac711c7c3ef7afcad0cde6c6e176d5a49ac30a1792b`). `HEADLESS_ARGV=PASS`, `SOURCE_AND_UI_HASHES=PASS`, `CANDIDATE_VERIFICATION=PASS`.
- **Release status:** `OLD_CONTAINER=STILL_STOPPED`, `DEPLOY=NOT_RUN`, `DOWNLOAD=NOT_RUN`. Next prepare separate exact image-only Compose override from preserved previous DLFR override, verify original 13 Compose inputs, environment, effective rendered configuration with only image difference, preserve prior image/manual rollback; then only the previously approved targeted service cutover with process/listener, job/TS and other-service postchecks. Fail closed on any mismatch; no SORA-489 retry.

## 2026-11-10 — DLSPD-001 CT108 guarded stop and one-image offline build PASS (NO DEPLOY)

- **Direct Teddy CT108 checks:** `CONTAINER_IDENTITY=PASS`, staged source digest `4c47ddafe6dcb7c478a47ac711c7c3ef7afcad0cde6c6e176d5a49ac30a1792b` PASS, unused candidate tag PASS, `ACTIVE_DOWNLOAD_GATE=PASS` with 13 tasks/0 busy, 0 FFmpeg processes and 1,395 protected TS, unrelated Gluetun/Selkies container identities/state PASS, available bytes `41002524672` and reserve+build budget PASS. Local base `dlspd001-local-base:b31b0b4d` pinned exactly to current source image ID `sha256:b31b0b4dd106abf19d3394b5d703391a7ea522151ae61622ec53b6a1c7b2d7a4`.
- **Maintenance stop:** Original running Downloader container `62ddcadf45be7a72f121c71802ddc10ada0beab849b7582568d2bee92147099c` stopped with `docker stop --timeout 45`; `DOWNLOADER_STOP=PASS`. Other containers left running. `OLD_CONTAINER=STILL_STOPPED` after build; no new download.
- **Exactly one local-only candidate build:** `docker build --pull=false --network=none` with one-source overlay and Python syntax/SHA guard completed steps 1/3 base from the pinned current image, 2/3 COPY `teddy_spoofdpi.py`, 3/3 Python compile and `HEADLESS_SOURCE_HASH=PASS`. New tag `dlspd001-headless-candidate:20261110`, image ID `sha256:7f115859edaa5eb9bd657f74c60741db5ac9d66fdb9667982e67bc7a0a95676f`. `IMAGE_BUILD=PASS`, `DEPLOY=NOT_RUN`, `DOWNLOAD=NOT_RUN`. Build CLI output itself is not complete image runtime/UI/Compose parity or product PASS.
- **Next:** Read-only candidate image runtime config, exact source and unchanged deployed API/UI hash comparison; stage separate private image-only Compose override with current API image rollback identity, compare effective Compose image-only delta, then single approved Downloader-only promotion. If any gate fails, keep original stopped and report; no blind retry/rollback, no P08 UI promotion or DLHLS new-ID POST.

## 2026-11-10 — DLSPD-001 isolated bridge headless listener PASS, production still unchanged

- **Teddy CT108 evidence:** Disposable `docker run --rm -i --pull=never --network=bridge --cap-drop=ALL --security-opt=no-new-privileges` from exact current base image invoked `spoofdpi --no-tui`; inside isolated container `PROXY_LISTENER=OPEN`, `EARLY_EXIT_CODE=None`, `HEADLESS_BRIDGE_TEST=PASS`, `TEST_PROCESS_CLEANUP=PASS`. Original `missav-dlp-web` image and running state stayed unchanged at end; `DOWNLOADER=STILL_RUNNING`, `IMAGE_BUILD=NOT_RUN`, `DEPLOY=NOT_RUN`, `DOWNLOAD=NOT_RUN`.
- **Boundary:** Prior stricter `--network=none` + `--cap-drop=ALL` test failed exit1; its sanitized first 500 chars showed normal config-warning/HTTP-mode startup, but suppressed error tail, so specific cause not proven. Bridge result verifies the same installed binary and headless flag can establish localhost listener in a more representative isolated network. This is **not** production source-site reachability or HLS trial PASS.
- **Next authorized action:** Fresh CT108 no-active-task/FFmpeg and space+reserve/other-service gate, then A-method stop only Downloader, one offline small image-from-current-base with only staged `teddy_spoofdpi.py`, verify exact source/UI/API/runtime config and preserve rollback, and separately apply image-only Compose to Downloader if all gates PASS. No original failed jobs/1,395 TS mutation or retry.

## 2026-11-10 — DLSPD-001 isolated headless binary listener probe failed under restrictive sandbox (NO STOP/BUILD)

- **Teddy CT108 result:** A disposable `docker run --rm -i --pull=never --network=none --cap-drop=ALL --security-opt=no-new-privileges` with the proven current image invoked `spoofdpi --no-tui` as a subprocess; `PROCESS_EXITED_EARLY=True`, `LOCAL_PROXY_LISTENER=CLOSED`, then `AssertionError: HEADLESS_PROXY_NOT_READY`. The script suppressed stdout/stderr so exit code/error cause unknown. Fail-closed: `HEADLESS_RUNTIME_TEST=NOT_PASS`; outer command stopped before post-test current-service identity check.
- **Interpretation:** The disposable test network/capability restrictions differ from actual production Compose and could themselves cause early exit. This observation **does not prove** `--no-tui` is ineffective in real runtime; do not proceed with build or service stop until a bounded **same-isolation** sanitized stderr/exit-code diagnostic identifies the blocker, then decide proportional representative testing. No change to current Downloader, 3 jobs or TS was requested by this test.
- **Current release state:** staged source `SOURCE_STAGE=PASS`; `DOWNLOADER_STOP=NOT_RUN`, `IMAGE_BUILD=NOT_RUN`, `DEPLOY=NOT_RUN`, `DOWNLOAD=NOT_RUN`. Next isolated read-only diagnostic should suppress external network/real download and print only redacted failure details, then verify target still running. No retries.

## 2026-11-10 — DLSPD-001 CT108 private one-file source stage PASS (NO STOP/BUILD)

- **Teddy CT108 operation:** Private staging directory `/opt/missav-dlp-web/backups/dlspd001-headless-tAZ957uv`, sourced by `docker cp` only from current running Downloader's `/app/teddy_spoofdpi.py`. Input source SHA256 `ba0a04d5ef952a1b388242154d50daf857a1347508ae39633292c6291d8534ac`; exact single call edit and docstring correction produced verified staged output SHA256 `4c47ddafe6dcb7c478a47ac711c7c3ef7afcad0cde6c6e176d5a49ac30a1792b`, byte-identical to GitHub `ca2e5236` source.
- **Transparent failed first check:** First source-staging copy remained unmodified because a prior ChatGPT command mistakenly omitted two SHA hex characters (`c3`) from the expected 64-char new digest, causing fail-before-write. Teddy ran corrected exact digest (`len=64`) and got `ORIGINAL_SOURCE=PASS`, `HEADLESS_PATCH=PASS`, `GITHUB_SOURCE_HASH=PASS`, `SOURCE_STAGE=PASS`. No service/source/binary runtime mutation from this staging step.
- **State:** `DOWNLOADER_STOP=NOT_RUN`, `IMAGE_BUILD=NOT_RUN`, `DEPLOY=NOT_RUN`, `DOWNLOAD=NOT_RUN`. Next conditional gated maintenance stop/one local-base offline Docker candidate build; preserve existing live image, rollback and all protected job/TS data. No source-page GET or real retry.

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
