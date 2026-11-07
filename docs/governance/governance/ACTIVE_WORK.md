# Governance workstream — active work

## 2026-11-07 — P08LIB-001 CSS-only production promotion PASS; real visual/API acceptance still pending

- **Real Teddy CT108 deploy output:** `LIVE_PREFLIGHT=PASS`, `ROLLBACK_PREPARED=PASS`, `ONLY_IMAGE_CHANGED=PASS`, `FINAL_GATE=PASS`, `COMPOSE_UP=PASS`, `POSTDEPLOY_RUNTIME=PASS`, `OTHER_SERVICES_UNCHANGED=PASS`, `ROLLBACK_READY=PASS`, `DEPLOYMENT=PASS`, `PRESERVE_ALL_BACKUPS_AND_IMAGES=YES`. This is user-supplied execution evidence, not ChatGPT/Codex operating the host. No automatic retries or rollback were performed.
- **Exact new live Downloader image:** `sha256:e2b5918e582397bf9a146319626d069437f89559933a261bb223849bfcf732e0`, tagged `missav-dlp-web:p08lib-css-1c1c062e-20261107-buildonly`, based on source commit `1c1c062e58f54519caad52d46303c11c6f6e424b`. New container ID `75acda1823ed5085a7e819c16dc3a2309150d6e30dc65516684f59ec9a3d1b91`. Original runtime image `sha256:146e6bc04ff52e38a14483a4e3bc0eb06df4571bd6e40e4f0a52534d9ecdec31` retained with tag `missav-dlp-web:p08lib-buildonly-3a249f4917d1-r2-20261107`, and earlier image `sha256:ba31ba9cfcc481dc1f658312a3155a3496856008ff4d52f5a652de0766fd0dbe` retained.
- **Distinct fresh rollback:** `/opt/missav-dlp-web/backups/p08lib-css-deploy-20261107-3sgbmcns`, contains rollback metadata and candidate/rollback overrides. Do not delete or prune existing images/backups. Original rollback directory `/opt/missav-dlp-web/backups/p08lib-deploy-20261107-b92t5ncp` must remain intact.
- **Scope / invariants:** New Compose effective settings changed only the allowed image value; bind mounts, environment map, ports, network attachments, Writer group/socket, restart policy, Stage9 timer and Gluetun + both Selkies container identities stayed as before. The single-service `missav-dlp-web` container was recreated once; prior unrelated containers/DB/NAS/Jellyfin/Stage11 untouched.
- **Pending (DO NOT MARK COMPLETE):** `LIVE_PC_MOBILE_UI=NOT_RUN` and `AUTHENTICATED_API=NOT_RUN`. Product/UI visual acceptance still `INCOMPLETE`. Next: representative desktop/mobile live holdings summary 5 cards wrapping naturally (no narrow stacked column or huge blank gap), dark tab contrast, lists/search visible, Library DB tab; then read-only authenticated Library API checks. No further build, Compose mutation, media/DB writes or deletion until separate diagnosis if checks fail. Shared task `P08LIB-001 / IN_PROGRESS` unchanged.

## 2026-11-07 — P08LIB-001 exact-image CSS build PASS, no new deployment (Teddy CT108 log)

- **Teddy's actual CT108 command/log:** `BUILD_PREFLIGHT=PASS`, `SOURCE_IDENTITY=PASS`, `PROTECTED_LOCAL_WORKTREE=UNTOUCHED`, `DOCKER_BUILD=PASS`, `CSS_IMAGE_IDENTITY=PASS`, `PRODUCTION_UNCHANGED=PASS`, `BUILD_CHECKPOINT=PASS`, `DEPLOY=NOT_RUN`. Dockerfile finished step `[stage-0 80/80]`; test admin synthetic `8 PASS / 0 FAIL`; image exported and unpacked successfully. This is real user-provided output, not ChatGPT/Codex running Docker.
- **Pinned source:** exact canonical commit `1c1c062e58f54519caad52d46303c11c6f6e424b` from isolated archive `/tmp/p08lib-css-build-20261107-D5ED1k6m/source`. Build log `/tmp/p08lib-css-build-20261107-D5ED1k6m/build.log`. Dockerfile Git blob `52621b2cc7d6312038e3532ac30104737c7497ae`; CSS blob `b0c199bddfcf09a555b74a5e0e3585d0dc868d5e`.
- **New image:** local tag `missav-dlp-web:p08lib-css-1c1c062e-20261107-buildonly`; exact Docker image ID `sha256:e2b5918e582397bf9a146319626d069437f89559933a261bb223849bfcf732e0`. Embedded CSS SHA256 equals source CSS SHA256. Existing production image remains `sha256:146e6bc04ff52e38a14483a4e3bc0eb06df4571bd6e40e4f0a52534d9ecdec31`; Gluetun and both Selkies unchanged at build checkpoint. Older rollback image `sha256:ba31ba9cfcc481dc1f658312a3155a3496856008ff4d52f5a652de0766fd0dbe` remains protected.
- **Authorization unchanged:** Teddy has expressly approved visual verification and a new exact-source image build plus Downloader-only production promotion under shared `P08LIB-001` (governance/downloader/discovery-writer-safety/stage9-media). Approval does not cover other containers/Writer/Stage9 timer/Stage11/NAS/DB/Jellyfin, media jobs, deletion, broad rollback, source modification or second build. No new deployment was carried out by this record.
- **Remaining checks:** newly built image is correct as a built artifact, but representative PC/mobile visual rendering and post-deployment authenticated Library API are not verified. Actual new-image deployment and production UI acceptance are both `NOT_RUN`. Do not report production PASS.
- **NEXT one checkpoint:** preserve existing rollback directory and make a fresh distinct backup of exact active Compose+current image; verify active jobs idle; compare effective Compose/ports/mounts/env/network+other-container IDs with image-only override before changing anything. If safe, perform `missav-dlp-web` single-service exact new-image promotion and immediately read-only postcheck. If postcheck differs, stop and inspect; no blind rerun or destructive cleanup.

## 2026-11-07 — P08LIB-001 CT108 read-only prebuild preflight PASS (Teddy's real terminal)

- **Exact source approval checkpoint:** GitHub canonical `teddy-subtitle-stage11` was `bfc59896fd2053f7a5e6cc8753516d69d9a5c10b`, existing approved CSS correction `27de4f0c44f0ef2cd10fdee97501b6cb377577a9`. Teddy's `root@downloader` provided `REPOSITORY=PASS`, `REMOTE_SHA=PASS`; local branch `teddy-subtitle-stage11`, local HEAD `b1bc851f` and `LOCAL_WORKTREE=DIRTY_PROTECTED`. Do not checkout/reset/pull/clean local protected dirty worktree; use a separate SHA-pinned `git archive` after a safe fetch, if needed.
- **Actual production state at read-only checkpoint:** `CURRENT_IMAGE=PASS` (sha256:146e6bc04ff52e38a14483a4e3bc0eb06df4571bd6e40e4f0a52534d9ecdec31), `RUNNING=PASS`, `NO_RESTART_LOOP=PASS`, `WRITER_GROUP=PASS`, `MOUNTS_14=PASS`, `COMPOSE_FILES_12=PASS`. Gluetun, desktop Selkies, mobile Selkies IDs/status `PASS`; backup directory+three metadata/overrides `PASS`; prior image sha256:ba31ba9cfcc481dc1f658312a3155a3496856008ff4d52f5a652de0766fd0dbe preserved.
- **Worker and resource evidence:** `WRITER_SOCKET=PASS`, `STAGE9_TIMER=PASS`, Stage9 service `inactive` (normal timer-idle state); reported task counts `{'완료': 1}` and MP4 queue counts `{}`; Docker free space `39.48 GB`, available RAM `4.81 GB`. `PREFLIGHT=PASS`, `NO_CHANGES_MADE=READ_ONLY`. No user data/content mutations.
- **Scope:** Existing four-workstream shared `P08LIB-001 / IN_PROGRESS` exact CSS-source image build + single-Downloader promotion approval remains in force; Stage11 is independent. This preflight is **not** the image build/deployment/visual UI acceptance. Do not silently replace the historical postcheck assertion failure; keep it recorded as unresolved origin while present runtime parity has separately passed.
- **Next one checkpoint:** one isolated Docker image build from fresh exact canonical SHA (documentation-only commit follows this note) via an archive, preserving dirty source/operating containers. Build Dockerfile unchanged, emit distinct tag, inspect output and running-service invariants. No deployment until that result is evaluated.

## 2026-11-07 — P08LIB-001 visual validation + one exact-source image build/Downloader-only promotion expressly approved

- **User authorization (current):** After reviewing the GitHub CSS source correction and doc checkpoint, Teddy explicitly stated: `화면 검증과 새 이미지 빌드 배포 모두 승인해`. This supersedes ONLY the previous `no new build/redeploy` restriction for the exact P08LIB holdings-UI CSS correction, within the same registered shared task `P08LIB-001 / IN_PROGRESS` across governance, downloader, discovery-writer-safety and stage9-media. Does not authorize unrelated source/contracts/router changes, data mutations, or subtitle work.
- **Approved source:** canonical branch `teddy-subtitle-stage11`, last product CSS commit `27de4f0c44f0ef2cd10fdee97501b6cb377577a9`, followed by documentation checkpoint `8c124e43097f646b02d63d7b81b93d779c280e31`. Only product delta since the previously deployed source is `templates/teddy-library.css` full-width summary + dark-mode file-management tab contrast. Use clean git-archive exact canonical SHA after this approval record, preserving frozen previous images; avoid dirty checkout and unapproved product edits.
- **Authorized sequence and safeguards:** (1) Real CT108 read-only exact origin/SHA, approved shared task contracts, runtime image/container+other-service IDs, composed settings, attached files/DB/NAS, existing Writer socket/Stage9 timer, current download/remux/queue safety, backup and capacity preflight. (2) One clean, newly tagged isolated Docker image build using the existing unchanged Dockerfile and build-time smoke gates, verifying content and identity. (3) A bounded representative PC/mobile UI layout/contrast check on the candidate where technically feasible, without destructive actions. (4) Provided gates pass and live service idle/safe, exact-image single-service `missav-dlp-web` promotion with image-only override preserving the 11 previous Compose files/mounts/settings, no dependencies recreated. (5) Read-only live authenticated Library API and real PC/mobile visual check; compare current image and other-service identity, record result and preserve rollback.
- **Allowed on safety failure:** STOP, report exact reason; leave running image untouched. If promotion already happened and postchecks fail, do not blindly rerun or roll back; verify live state and only execute exact safe rollback when proven possible. No service-wide Compose down, image prune/pull, queue/retry/resume, media/NAS/Jellyfin/DB edits, Stage9 timer/Writer socket mutation, Stage11 work, or actual UI permanent delete.
- **Acceptance:** All checked image/build/source and single-service/other-service/runtime invariants PASS; representative PC and mobile holdings display the five summary cards across available width or responsively wrapped, content directly below, dark-mode tabs readable; read-only Library API matches existing holdings. Distinguish visual evidence from static smoke, and technical build/deploy PASS from full product PASS. Record checks on exact image, not just source.
- **Status:** APPROVAL_RECORDED; NO NEW BUILD/DEPLOY HAS BEEN RUN by this record. Existing running image remains `sha256:146e6bc04ff52e38a14483a4e3bc0eb06df4571bd6e40e4f0a52534d9ecdec31` as last verified by Teddy. Existing rollback `/opt/missav-dlp-web/backups/p08lib-deploy-20261107-b92t5ncp` must be retained; before any new deployment create a distinct preserved rollback record. Current next checkpoint is read-only CT108 preflight, not a mutating command.

## 2026-11-07 — P08LIB-001 approved CSS source-only correction, visual check pending

- Teddy's real CT108 read-only post-deploy verification: RUNTIME_CHECKS=PASS, image sha256:146e6bc04ff52e38a14483a4e3bc0eb06df4571bd6e40e4f0a52534d9ecdec31 active, settings/mounts/other containers/Writer socket/Stage9 timer PASS; LIVE_UI_API=NOT_RUN.
- User screenshots: holdings summary cards collapsed into narrow right column with large blank area; dark-mode file-management tabs too faint. Runtime markup/CSS read-only markers LAYOUT_MARKUP, FLEX_LAYOUT, SUMMARY_SHRINK_BLOCK and CARD_GRID PASS; DARK_TAB_OVERRIDE=NOT_FOUND.
- Teddy explicitly approved source-only CSS fix, PC/mobile validation and GitHub promotion; NOT a Docker build or redeploy.
- Exact product commit: 27de4f0c44f0ef2cd10fdee97501b6cb377577a9. Only templates/teddy-library.css changed: full-width holdings summary, dark file-management tab contrast. Existing auto-fit 170px metric grid and responsive breakpoints untouched.
- Source structural assertions 8/8 PASS, GitHub changed-file readback PASS, mobile stylesheet has no conflicting selectors. Actual PC/mobile rendered visual tests and live authenticated API NOT_RUN. Source fix is NOT YET in current running Docker image; product/UI acceptance remains INCOMPLETE.
- Protected: no Docker build/rollback/redeploy, NAS/DB/Jellyfin/Writer/Stage9/Stage11 operations, download queue actions or deletion. Preserve rollback at /opt/missav-dlp-web/backups/p08lib-deploy-20261107-b92t5ncp. Shared P08LIB-001 IN_PROGRESS and separate Stage11 S11-WX011 unchanged.
- NEXT: isolated PC/mobile visual check of exact committed source; new Docker build/deployment require separate explicit approval. Previous postcheck AssertionError remains historically unresolved; do not relabel it as diagnosed.

## CURRENT P08LIB-001 CT108 SINGLE-SERVICE DEPLOY ATTEMPT — POSTCHECK ASSERTION FAILURE (2026-11-07 KST)

- **Real CT108 output supplied by Teddy (not a Codex execution):** The previously approved precise P08 Docker service-only promotion script was run at `root@downloader`. It reported `LIVE_PREFLIGHT=PASS`, `DEPLOY_CONFIG_ONLY_IMAGE_CHANGED=PASS`, `ROLLBACK_PREPARED=PASS`, and `COMPOSE_UP=PASS`; then `PHASE=APPLY_ATTEMPTED`, `DEPLOYMENT=CHECK_REQUIRED`, `ERROR_TYPE=AssertionError`, blank `ERROR=`, `NO_AUTOMATIC_ROLLBACK=SAFETY`.
- **Rollback artifacts:** `/opt/missav-dlp-web/backups/p08lib-deploy-20261107-b92t5ncp`. Retain the source image `sha256:ba31ba9cfcc481dc1f658312a3155a3496856008ff4d52f5a652de0766fd0dbe`, candidate `sha256:146e6bc04ff52e38a14483a4e3bc0eb06df4571bd6e40e4f0a52534d9ecdec31`, 11 original Compose files, candidate and rollback JSON overrides, and metadata; no secret values to be written to canonical docs.
- **Important status distinction:** Docker Compose `up -d --no-deps --no-build --pull never --force-recreate missav-dlp-web` returned success, which indicates the one-service recreation command completed; **the failing assertion is not yet identified**. No evidence yet whether the exact new image is actually running healthy, whether all settings/other service IDs match, or whether read-only UI/API checks pass. **Do not report `DEPLOYMENT=PASS` or `DEPLOYMENT=FAILED` without post-state evidence.** The old container may have been replaced already.
- **Safety:** Explicitly **do not rerun the mutating deploy script**; do not initiate automatic/manual rollback until read-only state is inspected; preserve all files, queue, DB, NAS, credentials, Git worktrees and Stage9/Writer/Stage11. P08 shared approval and contract/version/task state remain unchanged. No additional build/pull/prune.
- **Next single checkpoint:** Read-only inspect the running Downloader ID, `.Image`, status/restart/health, exact old/new image IDs, live image tag, required mount/network/group/ports and environment parity using **maps rather than order-dependent lists**, other three container IDs/start timestamps, Stage9 timer/service, Writer socket, and rollback directory files. Display PASS/CHECK_REQUIRED by category, not secret values. If the root cause is a nonsemantic environment list ordering difference, verify actual key/value equality without printing values. After diagnosis, decide a safe next action; **`LIVE_UI_API=NOT_RUN`**, `DEPLOYMENT=CHECK_REQUIRED`.

## CURRENT P08LIB-001 EXACT-BUILT-IMAGE PRODUCTION PROMOTION — TEDDY APPROVED (2026-11-07 KST)

**Explicit user approval:** After the verified one-time P08 Docker build PASS and GitHub evidence commit `32c029493733f6df356f7e5755d9994730f80ae1`, Teddy answered **"응 승인해"** to the proposed next phase: promote **the already-built exact P08 image** to the running Downloader only, keep existing production image as rollback, and then perform a brief real PC/mobile Library UI and authenticated API check. The shared task stays `P08LIB-001 / IN_PROGRESS`, requiring `governance,downloader,discovery-writer-safety,stage9-media`; independent Stage11 `S11-WX011` and all contracts/router remain unchanged. This is **approval to prepare and execute a carefully gated promotion**, not evidence that any deployment has happened.

### APPROVED_SCOPE — EXACT-IMAGE DEPLOYMENT WITH PRECONDITIONS
- **Release candidate:** locally built CT108 tag `missav-dlp-web:p08lib-buildonly-3a249f4917d1-r2-20261107`, expected exact Docker image/index ID `sha256:146e6bc04ff52e38a14483a4e3bc0eb06df4571bd6e40e4f0a52534d9ecdec31`, revision label `3a249f4917d122b95b67ae42fb52ce16f9d96a7d`, build log `/tmp/p08lib-build-r2-UaeJAav1/build.log`. Build was already completed; **do not rebuild/pull/retag/prune** it.
- On real CT108 `root@downloader`, first perform **read-only** preflight of the exact local image ID/revision and relevant application files, live Downloader and Gluetun/Selkies identities, current effective Compose file set/overrides/service/config, active download/remux/queue states, persisted work/NAS mounts, Writer connectivity/mount/group, Stage9 timer/service and disk/memory safety. Stop without mutation on identity drift, unsafe active jobs, missing rollback image, incomplete Compose provenance or uncertain backups. Confirm protected running image is still `sha256:ba31ba9cfcc481dc1f658312a3155a3496856008ff4d52f5a652de0766fd0dbe`, unless a later independently verified source-of-truth supersedes this approval.
- Preserve an exact rollback path to the existing image and all original effective Compose configuration, mounts, network, environment/secret references, ports, group permissions, working storage and service dependencies. Any backup created must avoid exposing credentials and must not overwrite pre-existing artifacts. Do not wipe, reset or mutate application queues/jobs.
- Once preflight and rollback checks pass, change/recreate **only Docker service/container `missav-dlp-web`**, using the exact existing Compose configuration plus only a narrowly scoped image selection for the above frozen candidate; allow no dependent service re-create/update. Do not restart or alter `gluetun-missav`, either Selkies container, external Writer, Stage9 timer/service or Stage11.
- Immediately compare image/container identity, required mounts/settings and dependent container before/after snapshots, confirm Downloader running without restart loop, and do minimal authenticated read-only `/api/library` and browser PC/mobile Library UI checks (five present-holdings cards, NFO/poster/subtitle sections, existing file navigation/play/download and permanent-delete protections **without performing a delete**). Report Stage9 status `UNKNOWN` rather than inventing counts if its DB is not mounted. Preserve the historical Stage12 status panel and distinction from current holdings.
- If actual rollout fails and a safe exact rollback can be demonstrated from the preserved Compose/image (no destructive effect on active jobs), restore the original Downloader image only and verify it. If rollback conditions are uncertain, **stop and report** rather than guess or loop.

### PROHIBITED_SCOPE
No Docker build/retry, code or smoke edits, Dockerfile/requirements modification, remote image push/pull, service-wide `compose down/up`, Docker system prune, old image or log cleanup, app queue recovery/resume/retry, downloads, Writer socket lifecycle changes, Stage9 worker/timer actions, NAS/Jellyfin/production DB writes, subtitle model/publication, actual file deletion or destructive UI test. Preserve all existing files and state.

### ACCEPTANCE / EVIDENCE / NEXT
- `DEPLOYMENT_APPROVAL=YES`; `DEPLOYMENT_EXECUTION=NOT_RUN` until CT108 real logs confirm actual image promotion. Prior `BUILD_ONLY=PASS` and `RUNNING_CONTAINERS_UNCHANGED=PASS` remain unchanged historical evidence.
- One checkpoint at a time: **NEXT immediate** = CT108 bounded read-only exact-image, operating Compose/service, queue and rollback preflight; then formulate/run a precise guarded deployment command using observed configuration. Record major execution and real UI/API outcome in these four ACTIVE_WORK files, `CURRENT_HANDOFF.md`, and `WORK_ROADMAP.md`.
- Production PASS requires actual container image identity/readiness, preserved services/data, and representative authenticated real Library UI behavior; not just image build or offline smoke PASS.

## CURRENT P08LIB-001 ONE-TIME ISOLATED DOCKER BUILD RETRY — REAL CT108 RESULT PASS (2026-11-07 KST)

- **Evidence:** Teddy's own CT108 `root@downloader` terminal transcript (not a Codex execution). Fresh origin `teddy-subtitle-stage11` matched exact source commit `3a249f4917d122b95b67ae42fb52ce16f9d96a7d`. Clean isolated `git archive` at `/tmp/p08lib-build-r2-UaeJAav1/source`; Dockerfile Git blob `52621b2cc7d6312038e3532ac30104737c7497ae`, navigation smoke blob `54cfab3332ee2a4975fa7d5e9b5be641675afcdf`, Overlay HTML SHA256 `63fb18077033ddd82e1785f2018622e5aeaf44007a8d8e34b550e50573b14733` all matched. `SOURCE_PREFLIGHT=PASS`.
- **Exactly one user-approved retry consumed:** unchanged Dockerfile and smoke, `docker build --progress=plain --pull=false`, tag `missav-dlp-web:p08lib-buildonly-3a249f4917d1-r2-20261107`. `BUILD_EXIT=0`. Dockerfile `77/80` navigation smoke PASS, `78/80` P08 final Overlay Library UI smoke PASS, `79/80` admin synthetic smoke `8 PASS / 0 FAIL`, `80/80` PASS; image export/unpack complete.
- **Built image identity:** `sha256:146e6bc04ff52e38a14483a4e3bc0eb06df4571bd6e40e4f0a52534d9ecdec31`; Docker-reported `SIZE=346117613` bytes; OCI revision `3a249f4917d122b95b67ae42fb52ce16f9d96a7d`; build log `/tmp/p08lib-build-r2-UaeJAav1/build.log`. Prior failed log `/tmp/p08lib-build-ivpIA4gM/build.log` and earlier images were not cleaned/pruned by the build command.
- **Operational invariance:** `RUNNING_CONTAINERS_UNCHANGED=PASS` (Downloader, Gluetun, desktop/mobile Selkies); `COMPOSE_UNCHANGED=PASS`; Stage9 timer `active/waiting`, service `inactive`, `Result=success`. The build did not deploy/recreate/restart services, modify application/source/tests, or write NAS/DB/Jellyfin/Writer/Stage11.
- **Outcome:** `BUILD_ONLY=PASS`; `APPROVED_RETRY=CONSUMED`; `DEPLOY=NOT_RUN`; `LIVE_P08_BROWSER_UI=NOT_RUN`. Technical build PASS is not product acceptance. Preserve both new and old images; running production image remains `sha256:ba31ba9cfcc481dc1f658312a3155a3496856008ff4d52f5a652de0766fd0dbe`. Keep shared `P08LIB-001 / IN_PROGRESS`, `REQUIRES_WORKSTREAMS: governance,downloader,discovery-writer-safety,stage9-media`, all contracts/router and separate Stage11 untouched.
- **NEXT_DECISION:** Teddy must separately approve any further isolated image-content check and eventual exact-image production deployment with rollback plus limited authenticated UI/API validation. No second build retry, automatic promotion or cleanup is authorized.

## CURRENT P08LIB-001 ONE-TIME ISOLATED DOCKER BUILD RETRY — TEDDY APPROVED 2026-11-07 KST

**Explicit user approval:** Teddy answered "승인해" to a request for exactly **one additional isolated Docker image build attempt** after the previous source-pinned build failed at Dockerfile `77/80` on a stale navigation smoke label. This supersedes only the exhausted *single-build-attempt limit* of the 2026-11-06 P08 build-only phase, not its no-deploy/no-write/source-freeze protections. Shared workstream identity remains `P08LIB-001 / IN_PROGRESS`, requiring `governance,downloader,discovery-writer-safety,stage9-media`. Contracts/router and unrelated workstreams remain unchanged.

### APPROVED_SCOPE — ONE RETRY ONLY
- Prior fix `teddy_file_management_navigation_smoke.py` was promoted at `0549f2e475a85aa46d025f4b1e2a5a24aab9f1f1`; real CT108 SHA-pinned two-phase `BASE_HTML_SMOKE=PASS` and `FINAL_OVERLAY_SMOKE=PASS` were supplied by Teddy; handoff-readback checkpoint was `ea6332d98cfeb28632314502ab9911e6298cd1cf`.
- After confirming newest canonical SHA and exact source identity, real CT108 (`hostname=downloader`, PID1 `systemd`), Docker/Stage9 state, running containers and RAM/disk budget, perform **one** uniquely tagged Docker build from a clean `git archive` of the exact promoted SHA in an isolated temporary directory with the **unchanged** Dockerfile, existing manifest and existing smoke tests. Preserve the former failed build log and all images/source candidates.
- Inspect build exit, smoke logs, final image ID and relevant source files, and compare before/after production container identity/state and Stage9 timer/service. If failure or material safety mismatch: stop; report and record evidence. No automatic second attempt.

### PROHIBITED_SCOPE
No application or test-source changes, skipping/relaxing smoke or manifest, Dockerfile/requirements edits, Docker Compose, live container deployment/recreate/restart, Stage9 timer/service changes, Writer socket actions, Stage11/Stage12 work, NAS/Jellyfin/DB reads beyond approved static boundaries or any writes, downloads, external publication, cleanup or image pruning. Docker build may only perform its existing declared build-time network/dependency operations.

### ACCEPTANCE_CRITERIA
One clean, exact-commit, uniquely tagged isolated Docker build completes all in-Dockerfile checks; generated image content/ID are recorded; Docker/Stage9 operational state remains unchanged. A build-only technical PASS is not a deployment or product/UI acceptance; deployment needs new explicit approval.

### EVIDENCE
Teddy approved the reattempt immediately following a real CT108 two-phase navigation smoke PASS and explicit question whether to retry one isolated Docker build. Previous failed build result and `/tmp/p08lib-build-ivpIA4gM/build.log` remain historical evidence, not deleted or overwritten.

### NEXT_DECISION
Review real CT108 one-build output; if PASS, decide separately whether to approve isolated image-content checks and eventual production deployment; if FAIL, require a fresh diagnosis/approval before another attempt.

## CURRENT P08LIB-001 ISOLATED DOCKER BUILD-ONLY PHASE — TEDDY APPROVED 2026-11-06 KST

Teddy explicitly approved the next **build-and-inspect-only** step after the six-file P08 canonical source promotion `a8e9156bfc0a966ea3af3778aacd11c02ec719fa` and documentation readback `651b90f8de42aa4ff32e7e5a0f28f53c01382811`. This temporarily supersedes the earlier P08 offline-only **Docker image build prohibition only for one bounded isolated build**; all other old protections and task boundaries remain. The four-workstream shared task remains `P08LIB-001 / IN_PROGRESS`; contracts and router are unchanged.

## OBJECTIVE

Build the exact newly promoted P08 Downloader image in a new isolated clean source directory, verify its existing Dockerfile-provided smoke gates and image contents, and prove the running Downloader/Stage9/Writer/other services were not changed.

## APPROVED_SCOPE

- First verify fresh canonical `teddy-subtitle-stage11` HEAD, the six P08 product blob SHAs and matching four-workstream authorization; use a clean SHA-pinned isolated checkout, not the dirty old candidate or live operational source directory. Confirm real CT108 Docker/host available disk, memory, active jobs and safe build budget before starting.
- Use the existing unmodified Dockerfile and requirements, with a **unique non-operational build-only image tag**; do not reuse or replace the current production image/tag. An ordinary Docker build may install its declared dependencies and run its existing in-image tests. No unapproved code fixes after a failure.
- Record build exit, resulting image ID/size and source content/manifest for the final Overlay HTML, API, shared JS/CSS and relevant smoke files. Image-only inspect and, only if needed, a bounded disposable `--network none`, no-operational-mount, read-only-root test container are permitted; never launch the app or attach production sockets, directories, databases, NAS or Jellyfin credentials.
- Compare before/after read-only Docker container IDs/images/status/start times of running Downloader and companion services and Stage9 service/timer state. Preserve the built image and prior images for explicit later deployment/rollback decisions.
- Coordinate the shared authorization record, governance validation, canonical readback and later separate deployment decision only; no governance checker/contract/router edits.

## PROHIBITED_SCOPE

- No Docker Compose `up`/recreate/restart/deploy, existing image retag/replacement, production web access tests or login, service/timer start/stop, stage9 DB mount, Dockerfile/requirements/product source/test edits, extra OS/daemon changes, active job cleanup, image/backup prune/delete, real downloads, NAS/DB/Jellyfin write, Stage9 manual runner, Writer socket mutation, Stage11/Stage12 execution, governance contract/router/task changes. No forced retry of a failed build by modifying application code or relaxing tests. Stop on unsafe resources or identity mismatch.

## ACCEPTANCE_CRITERIA

- Exact branch/source/blob and matched P08 authorization preflight PASS; clean isolated checkout with unchanged production runtime.
- One unique build-only image completes with all mandatory existing Dockerfile smoke checks PASS, and image contents match promoted source; full build logs/output preserved without secrets.
- Production containers, their image IDs/start times, compose config and Stage9 timer unchanged. `BUILD_ONLY=PASS` does not assert browser/NAS/Jellyfin product acceptance or operational deploy PASS.

## EVIDENCE

- Teddy directly answered “응 승인해” to the specifically proposed isolated Docker image **build-only** stage on 2026-11-06 KST, after source promotion PASS and explicit warning that production deployment needs a later separate decision.
- Pre-approval canonical product commit `a8e9156bfc0a966ea3af3778aacd11c02ec719fa`; prior documentary HEAD `651b90f8de42aa4ff32e7e5a0f28f53c01382811`. No build has occurred from this authorization record.

## NEXT_DECISION

After bounded CT108 build-only evidence and user review, request a separate explicit approval for production Docker deployment, its rollback/monitoring plan, and live API/browser validation. Do not treat an isolated build PASS as deployment approval.

## CURRENT P08LIB-001 OFFLINE IMPLEMENTATION PHASE — USER APPROVED 2026-11-06 KST

Teddy explicitly approved P08 UI/API source implementation with representative **offline-only** tests after the verified joint registration and CT108 read-only runtime/mount preflights. This scoped implementation authorization supersedes the prior registration-only product-code prohibition **only for the allowed candidate files and offline tests**. Task ID `P08LIB-001` and four-workstream requires set remain unchanged. Coordinate this task's scope and evidence only; do not edit common contracts, router or governance checker.

Teddy's 2026-11-06 product decision: P08 poster metric means **NAS-local Primary image file exists**, not that every byte can be fully decoded. This explicitly supersedes the former temporary 'all recognized posters UNKNOWN until full decode' candidate workaround; the existence check must still fail closed on unsafe/missing evidence.

## OBJECTIVE

Produce a reviewable, bounded P08 library UI/API candidate with five honest current-holdings metrics and three clear status sections; prove representative offline behavior and keep existing user-data/runtime protections intact.

## APPROVED_SCOPE

- In a verified isolated worktree based on current `ssikgun/missav-dlp-web` `teddy-subtitle-stage11`, edit only P08 candidate source `teddy_library_api.py`, `downloader_runtime_overlay/templates/index.html`, `templates/teddy-library.js`, `templates/teddy-library.css` and existing directly relevant smoke files (e.g. `teddy_library_api_smoke.py`, `teddy_library_ui_smoke.py`, `teddy_file_management_navigation_smoke.py`). Do not rewrite root `templates/index.html` or unrelated source.
- Reuse the existing one-pass bounded NAS inventory, current holdings identity/KO/size semantics and additive `/api/library` response fields. Count valid sibling `DVD-ID.nfo` or legacy `movie.nfo` by bounded regular-file XML + matching movie ID checks; distinguish `VALID/ABSENT/INVALID/UNKNOWN`. Count NAS-local `poster/cover/folder/default/movie` Primary image **file presence** (recognized title-prefix variants and JPEG/PNG/WebP extensions) as `PRESENT/ABSENT/UNKNOWN`: `PRESENT` when a matching safe regular non-symlink file with nonzero size is confirmed by the existing bounded inventory (optionally with existing bounded format-signature evidence); `ABSENT` only for verified missing Primary; `UNKNOWN` when NAS listing/attributes/identity are unavailable or unsafe. This is **file existence**, not proof of image integrity. Do not perform full image decoding, format conversion, new mass SSH/file reads or per-request verification of all image bytes. `thumb.jpg` alone, source `cover_url`, or Jellyfin cached Primary does not qualify.
- Keep full-library summary denominator separate from search-filtered item list. Preserve `ko_present`, unresolved/no-subtitle detail, known/unknown storage bytes, mismatch/UNKNOWN behavior; do not count historical `media_jobs.COMPLETE` as live NAS sidecar presence.
- Build responsive five-card `보유 라이브러리` summary and `라이브러리 DB 현황` containing distinct subtitle, metadata and poster subsections. Keep the present Stage12 pipeline counts visibly separate from current-holdings counts. Preserve existing search/sort/filter/cover preview/playback/download and guarded permanent-delete DOM/handlers, PC/mobile layout.
- Stage9 task process details may be implemented as an optional read-only bounded query layer with injected SQLite path/connection for offline fixtures only; absent media DB (the current production web container has no mount) must report UNKNOWN without breaking library availability. Do not add a new mount or assume a DB-only bind reads WAL coherently.
- Run a small representative existing smoke/fixture set for valid `DVD-ID.nfo`, legacy `movie.nfo`, missing/invalid/conflicting/unsafe/unknown NFO, `poster.webp`, `cover.jpg`, `thumb.jpg`-only, Stage9 DB unavailable, summary count consistency, and UI/playback/delete safeguards. Run `git diff --check`; report actual commands, PASS/FAIL, changed files, constraints and remaining UNKNOWN.
- Preserve implementation candidate/diff in the isolated worktree for review; any canonical source promotion requires separate approval. Important findings may be recorded in existing canonical roadmap/handoff without exposing secrets or private title data.

## PROHIBITED_SCOPE

- No production Docker image build/deploy/recreate/restart or Compose/mount modifications. No Stage9 media DB mount, live DB read/write, NAS/DB/Jellyfin write, new scheduled job, service/timer change, forced library scan, downloads, existing poster/NFO regeneration, media deletion or backup deletion.
- No Stage9 media pipeline/worker code changes, Stage11/Stage12 model/ASR/translation/publication code change, Writer socket/lock/security code change, or common contract/router/task ID change.
- No source promotion or production action based solely on offline smoke PASS. Fail closed on unmatched identity, unsafe symlink/path, ambiguous duplicate sidecars, unbounded resource use or unknown status; never silently turn UNKNOWN into ABSENT.

## ACCEPTANCE_CRITERIA

- Verify canonical repo, branch, HEAD and all four shared workstreams `P08LIB-001` before candidate edits; Stage11 remains independent.
- Only allowed P08 source/related smoke files change in an isolated candidate; default API semantics remain additive and existing client keys unchanged.
- Representative offline cases and existing library navigation/HTML/script smoke pass; unrelated playback/download/permanent-delete protections remain intact; `git diff --check` PASS.
- Report test evidence separately from product status. Actual CT108 build, Stage9 DB job-state mounting, live API/NAS/Jellyfin visual validation and deployment remain NOT_RUN.

## EVIDENCE

- User approved offline implementation and tests directly after P08 read-only Docker and Stage9 host DB/mount checks, latest documented at canonical `c993d0135fd152f714e20406aa6f4eb3fa690fd8`. Earlier P08 shared-route registration `f1759073` Project Governance succeeded, and subsequent source-only preflight results are in `CURRENT_HANDOFF.md`.
- Current host Stage9 DB exists but running web Docker lacks any Stage9 DB mount; Stage9 uses WAL. UI totals must therefore be independent of Stage9 job DB access.

## NEXT_DECISION

Review the offline candidate diff and test results. Only after review/approval may promote source to canonical; Docker build/deployment and any new read-only Stage9 DB mount require further explicit approval and a fresh operational safety preflight. At P08 closeout restore the previous task IDs and routing from `c020a8a9bbf9ac05b34975894edb9dd5d630a275` without erasing history.

## CURRENT TEMPORARY P08 SHARED REGISTRATION — P08LIB-001 (2026-11-06 KST)

Teddy approved a bounded shared registration to prepare P08 library UI work before P04 consolidation. Temporary participants are Governance, Downloader, Discovery Writer Safety, and Stage9 Media; Stage11 is independent. Original assignments at parent `c020a8a9bbf9ac05b34975894edb9dd5d630a275` are preserved and recoverable: Governance INACTIVE/NONE, Downloader+Writer Safety IN_PROGRESS/DLDWS-001 as a pair, Stage9 IN_PROGRESS/STG9MEDIA-001. This temporary transition does not close, cancel or overwrite original approved work/evidence; those task IDs will be restored at explicit P08 closeout.

## OBJECTIVE

Register a consistent shared task for P08 NFO/poster library-status UI and prepare a minimal implementation/verification plan while preserving existing behavior. Governance registration and original-task restoration evidence only.

## APPROVED_SCOPE

- Perform registration-only governance metadata and handoff/roadmap updates; validate all four participants with a single `P08LIB-001` and `REQUIRES_WORKSTREAMS=governance,downloader,discovery-writer-safety,stage9-media`.
- Review canonical Overlay `templates/index.html`, shared library JS/CSS, `teddy_library_api.py`, existing library/Stage12 read-only state, and Stage9 v1.0.9 source-of-truth rules; propose additive summary/status fields and bounded tests.
- Distinguish actual NAS-local NFO XML/movie ID validity and recognized NAS-local Primary files from historical `media_jobs` rows, remote `cover_url` or Jellyfin cached Primary. Count valid legacy `movie.nfo` as well as `DVD-ID.nfo`; `thumb.jpg` alone is not local Primary. Unknown inventory stays UNKNOWN, not false ABSENT.
- Preserve current file-manager search, sort, preview, playback, download and permanent-delete protections; preserve the current Stage12 subtitle processing panel and its different population of records.
- Preserve all current Stage9 scheduled operation, historical task evidence, Stage11 independence and Writer socket lifecycle. Make no production operation as part of registration. Seek separate explicit authorization to change product source, build or deploy.

## PROHIBITED_SCOPE

- No product source edits or test-code edits **in this registration-only phase**. No Docker build/deploy/restart, live API/NAS scan, actual download, Stage9 manual runner/timer/service changes, Stage11 model/subtitle changes, Writer code/socket changes, operational DB/NAS/Jellyfin writes, sidecar regeneration, deletion, cleanup, or backup modifications.
- Do not weaken approved Stage9 local Primary/no-overwrite/Jellyfin separation, Downloader or Writer safeguards, alter any approved contract, or infer an actual media completion count from stale DB job rows.
- Do not advance P04/P05/P06/P07 or treat previous workstream IDs as simultaneously active while this temporary route is registered.

## ACCEPTANCE_CRITERIA

- Router and all four ACTIVE_WORK metadata blocks match `P08LIB-001` and the identical four-workstream requirement; Stage11 S11-WX011 and all contract versions remain unchanged.
- Governance structural and smoke validations PASS; normal fast-forward commit and exact canonical remote SHA/readback PASS.
- Parent `c020a8a9bbf9ac05b34975894edb9dd5d630a275` preserves previous task metadata and historical evidence without deletion; scope and restoration steps are recorded.
- No product code, timers, containers, DB, NAS, Jellyfin or Stage11 source change; implementation/deployment gates remain distinct.

## EVIDENCE

- Teddy explicitly accepted the P08 Downloader+Stage9 shared route after static source/data design proposal `c020a8a9`; original routes anchored at `c020a8a9bbf9ac05b34975894edb9dd5d630a275`.
- Prior one-time `DLDLIB-001` transition demonstrated temporary Governance/Downloader/Writer alignment and later restoration under the existing router. Writer Safety joins solely to maintain previous DLDWS-001 pairing and verify non-interference; it owns no P08 product changes.
- This registration contains no production/runtime evidence. Source audit and proposed design are documented in the handoff and roadmap.

## NEXT_DECISION

After registration is verified, request explicitly scoped approval for offline P08 UI/API source implementation and representative smoke tests. Check actual deployed Docker UI and read-only Stage9 database availability before deciding status integration; ask separately for Docker deployment/live validation. At P08 closeout restore Governance INACTIVE/NONE, Downloader+Writer Safety DLDWS-001 pair, Stage9 STG9MEDIA-001; preserve Stage11 S11-WX011 throughout.

WORKSTREAM: governance
TASK_ID: P08LIB-001
STATUS: IN_PROGRESS
CONTRACT_VERSION: 1.0.1
REQUIRES_WORKSTREAMS: governance,downloader,discovery-writer-safety,stage9-media

## STG9MEDIA-001 TEMPORARY CONTRACT AMENDMENT CLOSED — 2026-11-03

User authorizes only the Stage9 v1.0.3 narrow fourhoi.com exact DVD-ID candidate URL exception, governance validation and restoration. No common-contract or unrelated workstream changes; no production operations.

## STG9MEDIA-001 TEMPORARY GOVERNANCE CLOSEOUT — 2026-11-03 KST

User-approved one-time shared governance change completed for Stage9 Media contract v1.0.2: auto-created temporary thumbnail may be removed only after verified official poster is confirmed as Jellyfin Primary, with exact ownership/path/hash checks and fail-closed/manual-art protections. Governance route and task restored to INACTIVE/NONE; Stage9-only STG9MEDIA-001 remains IN_PROGRESS. This document closeout grants no implementation, deployment, NAS deletion, database write or Jellyfin image change. Actual automatic Jellyfin image replacement remains blocked by lack of atomic conditional API support or a separately approved explicit risk-policy change.

## DLDLIB-001 CLOSEOUT — 2026-10-28 KST

DLDLIB_CLOSEOUT=PASS: user approved closure after the production evidence recorded below: SIGINT shutdown exit 0, existing candidate image deployment, MAX_TITLES=500, authenticated library HTTP 200 and user-confirmed 252 titles displayed in the web UI. The independent API summary/items counts were not read; no broader product-quality completion is implied. The exact deployment and previous blocked-attempt evidence remain below and in canonical history.

ROUTING_RESTORED: Governance INACTIVE / NONE (requires governance); Downloader and Discovery Writer Safety IN_PROGRESS / DLDWS-001 (requires downloader,discovery-writer-safety). Stage9 remains IN_PROGRESS / STG9MEDIA-001 and Stage11 remains IN_PROGRESS / S11-WX011. The original DLDWS-001 purpose, status, approvals, candidates, evidence and backup preservation policy are retained. Earlier DLDLIB-001 scopes, approvals and next decisions below are historical and grant no continuing operation authority. This closeout only edits routing, active-work and handoff documents; it authorizes no code, Docker, NAS/DB/Jellyfin, Stage9, Writer, Stage11 or backup operation.

### ACCEPTANCE_CRITERIA

Restore and structurally validate all routes, pass DLDWS-001 paired and unchanged Stage9/Stage11 preflights and governance smoke, pass git diff --check, normal fast-forward and exact remote readback. Preserve all historical evidence. Original route details are independently anchored at pre-transition commit a7f90446094f6a703d88e5ebb3d3517a8a4ba2f7 and prior document blob IDs below.

### NEXT_DECISION

Governance is inactive; proceed with DLDWS-001 only within its original authorized scope. Any new scope or deployment requires its own authorization. No product/runtime activity is authorized by DLDLIB-001 closeout.


## HISTORICAL CLOSED DLDLIB-001 OPERATIONS — 2026-10-28 KST

The user explicitly authorized the bounded Downloader-only production image deployment below. This supersedes the earlier DLDLIB-001 coding-phase prohibition on image build/container replacement/restart only for this exact operation, conditional on every safety gate. Prior coding evidence, DLDWS-001 and backup policies are preserved. Governance coordinates authorization/evidence, Downloader owns the change, and Writer Safety participates only to verify Writer invariance and compatibility.

### APPROVED_SCOPE

- After this approval is validated, committed, fast-forwarded and read back from canonical, read-only recheck actual CT108 host/container identity, image, complete Compose project/service/image/network/environment/mount/privilege/command configuration (never expose secrets), current file SHA and byte equality with the canonical pre-fix file, old-image/config rollback, live downloads/remux/tasks and MP4 journals, startup replay of old failures/GANA, Discovery DB read-only accessibility, Writer socket and shared-lock compatibility, and independent Stage9 scheduling.
- Only when all gates including startup and rollback safety PASS: build a reproducible uniquely tagged single-file image layer based on the verified running image ID, replacing only /app/teddy_library_api.py with the canonical MAX_TITLES=500 version. No docker commit or full-source rebuild. Verify candidate import/constant and unchanged runtime configuration. Preserve the old image and Compose configuration; replace only the actual Downloader Compose service without dependency recreation and preserve command, networks, mounts, secrets, environment and permissions.
- Verify running container, constant 500, authenticated /api/library HTTP 200 with actual count, list count and default ordering, web File Management library display, and unchanged jobs/queue/journal, Writer and Stage9 status. Any rollback requires a safe startup/replay path and preserved current state; stop if unproven. Record outcomes and precise evidence in ACTIVE_WORK and canonical handoff. User-supplied baseline image sha256:9ceedeba292ae50980e6fb143589b7c0e12d1abf8c34d82fa49de8a5a500402f and file SHA-256 7847786d04ac9af4c533f4163633db837954b5d15f9723b53fe68c50f72ed055 are historical until freshly verified.

### PROHIBITED_SCOPE

No product source change beyond already published constant, unrelated service/container recreation, direct patching of running container, Docker commit, forced job/download/Organizer/Stage9 work, Writer socket/service modification, Stage9 timer/service changes, NAS/Jellyfin/Discovery DB/settings writes, task or queue edits/deletion, backup movement/deletion, Stage11 changes or broad refactoring. No build/deploy if any mandatory safety gate is unknown or fails; no unsafe rollback or startup replay workaround. Do not publish secrets.

### ACCEPTANCE_CRITERIA

Approval readback, all governance checks and clean diff PASS before operations; fresh baseline, restart replay and rollback safety PASS before image creation/deployment. Candidate contains only the approved file difference and reads MAX_TITLES=500; real API and authenticated web UI verification are separate outcomes. If UI is unverified, do not claim full completion. Preserve unrelated services/data. Report each gate independently, image IDs and canonical SHA.

### DLDLIB-001 SIGINT DEPLOYMENT — 2026-10-28 KST

- User requested reuse of candidate sha256:dd5d4e96f0292ff931edd8a239387d8de735243d13d942032ac8c8afacce2c77 and reported SIGINT handled, SIGTERM not handled, prior SIGKILL exactly 30 seconds after SIGTERM, and no PVE kernel OOM log. Those signal/OOM findings are user-supplied. Canonical base was a2a56ae58ab7a756b78643e1460989191cdeaf3d. All three DLDLIB-001 routes stayed IN_PROGRESS; Stage9 and Stage11 routes unchanged.
- User explicitly confirmed a maintenance window with no new download/retry and reconfirmed no running/waiting tasks. Pre-stop: original container ffc4bef1e013c4e784b96bc219f19f6c5491d22937ad138c378dc0c559d7c3b2, old image sha256:9ceedeba292ae50980e6fb143589b7c0e12d1abf8c34d82fa49de8a5a500402f, original library SHA-256 7847786d04ac9af4c533f4163633db837954b5d15f9723b53fe68c50f72ed055; task records 5 complete; JSON queue 0. Backed-up eight Compose files matched original bytes/order; saved environment, old-image identity and candidate override rendered with only image difference.
- docker stop --signal=SIGINT --timeout=30 exited promptly with container exit code 0, OOMKilled=false; no SIGKILL indicated. Post-stop five completed tasks, JSON queue 0 and no legacy .part.ts; tasks SHA-256 27f8d654589a43d9664a132b177fee46f6ac1a88740ef5c8a80c900cb2a447c1 and settings SHA-256 6c11ebcb949b0ad0c65a74af503bb421b2ee41979d72cde53e84c63b0fe115ee matched pre-stop. No large media content was read.
- DEPLOY=PASS: reused existing candidate and changed only Compose service missav-dlp-web with --no-deps --no-build --pull never. New running container f73ccdb2431f916163f99e289288e5c21b3f3572706f85151626bd4902430527 uses the candidate image; python -B import MAX_TITLES=500 and file SHA-256 fd615dafaa3ae91f39daa4653d7f8ebe55a154be032191bcb4390a75451708ee PASS. Post-deployment 25 runtime configuration comparisons passed, including env, image, command, network, ports, mounts, group, user, privileges and restart policy.
- LIBRARY_API=PASS for HTTP: production server logged authenticated user-session GET /api/library?sort=nas_added&order=desc HTTP 200. WEB_UI=PASS from user observation: File Management > held library displayed 252 titles. The separate API summary.total_titles/items counts were not independently read, and no broad product-quality claim follows from the UI observation.
- Post-start task/settings hashes unchanged, five tasks completed, JSON queue zero and four legacy MP4 files present. Writer socket connection passed; Writer and both Stage9 timers active. Old rollback image remains locally available; root-only saved Compose inputs/environment and original-image rollback procedure remain available; rollback was NOT_RUN. No new image build, forced download/recovery, deliberate NAS/DB/settings mutation, other container restart, Writer/Stage9 or Stage11 change occurred. The ordinary library request used its existing read-only NAS inventory path.
- DLDLIB-001 remains IN_PROGRESS across Governance, Downloader and Discovery Writer Safety. Preserve prior DLDWS-001 history and backup policy. User may end maintenance; any restoration of original routes requires a separate closeout step. Continue monitoring within existing task scope.

### DLDLIB-001 DEPLOYMENT RESUMPTION — STOPPED AT SHUTDOWN (2026-10-28 KST)

- User submitted authenticated /api/tasks HTTP 200 with 5 complete and no running/waiting work, zero MP4 JSON journals, and eight original Compose files backed up with matching effective configuration. During the single-user maintenance window the user reconfirmed five completed tasks and committed to submit no new download/retry until notified.
- Read-only checks confirmed container ffc4bef1e013c4e784b96bc219f19f6c5491d22937ad138c378dc0c559d7c3b2, old image sha256:9ceedeba292ae50980e6fb143589b7c0e12d1abf8c34d82fa49de8a5a500402f and library SHA-256 7847786d04ac9af4c533f4163633db837954b5d15f9723b53fe68c50f72ed055. All eight original/backup files matched; stored order and original image ID matched live container. Compose interpolation values were saved exclusively root-only mode 0600 at /opt/missav-dlp-web/backups/dldlib001-compose-inputs-20261028/compose-interpolation.env; original and backup renders matched and 28 compared runtime configuration properties passed. Root-only candidate override changes the image reference only; original rollback command dry-run targeted only the Downloader service.
- The candidate was built from the verified local old-image tag after confirming its ID. The first BuildKit attempt using FROM sha256:... failed to resolve the local image; a local-tag build succeeded. Candidate sha256:dd5d4e96f0292ff931edd8a239387d8de735243d13d942032ac8c8afacce2c77, tag missav-dlp-web:dldlib001-20261028-v1: old image layer prefix unchanged plus one layer; image config identical; isolated no-network read-only import MAX_TITLES=500 and library file SHA-256 fd615dafaa3ae91f39daa4653d7f8ebe55a154be032191bcb4390a75451708ee PASS.
- During the user-confirmed maintenance window, before shutdown the disk tasks file had five completed, SHA-256 27f8d654589a43d9664a132b177fee46f6ac1a88740ef5c8a80c900cb2a447c1; queue JSON count zero; no active child processes. Docker stop with 30-second timeout returned exit 137 and OOMKilled=true; normal shutdown was NOT established, cause/timing of the OOM flag is unknown. After stop, tasks hash/status, zero JSON jobs, settings SHA-256 6c11ebcb949b0ad0c65a74af503bb421b2ee41979d72cde53e84c63b0fe115ee and absence of .*.part.ts were verified. Large legacy MP4 files were not read or deleted.
- Because the required normal shutdown condition failed, candidate deployment was not performed. The same original container was restarted with docker start after the preserved post-stop state was checked: same container ID and old image, running, Flask startup logged; library file remains old SHA; tasks/settings hashes unchanged, five complete, zero queue JSON; Writer service and Stage9 timers active. The old library 503 fix remains unapplied; authenticated library and UI validation NOT_RUN. No new image was attached to production. STARTUP_REPLAY_SAFETY=BLOCKED and ROLLBACK_READY=BLOCKED for a future rollout until the abnormal stop is understood and a normal safe stop/restart can be established; CANDIDATE_IMAGE=PASS; DEPLOY=BLOCKED; LIBRARY_API=NOT_RUN; WEB_UI=NOT_RUN.
- No NAS/Jellyfin/Discovery DB write, task/queue manipulation, backup deletion, Writer/Stage9 change, forced download/recovery or Stage11 change was performed. DLDLIB-001 remains IN_PROGRESS across Governance, Downloader and Writer Safety; original DLDWS-001 approvals and backup policy are retained. The maintenance window can end because the original service was restarted. Next: investigate exit 137/OOM safely without disturbing service, establish normal shutdown evidence, then recheck all time-sensitive gates before any further deployment.

### DLDLIB-001 OPERATIONS PREFLIGHT — BLOCKED (2026-10-28 KST)

- GOVERNANCE_DEPLOY_AUTH=PASS: user-approved operations authorization was validated and fast-forwarded at 172c103b3a5216356d77a36b4094ecaa21eaef8a, then exact SHA/tree fetched back before live checks. User-provided facts remain distinguished from these read-only observations.
- IMAGE_BASELINE=PASS for identity and library code: current running container ffc4bef1e013c4e784b96bc219f19f6c5491d22937ad138c378dc0c559d7c3b2, image sha256:9ceedeba292ae50980e6fb143589b7c0e12d1abf8c34d82fa49de8a5a500402f; /app/teddy_library_api.py SHA-256 7847786d04ac9af4c533f4163633db837954b5d15f9723b53fe68c50f72ed055 equals canonical pre-fix bytes. Runtime image command python teddy_bootstrap.py; restart unless-stopped. Canonical fix SHA-256 fd615dafaa3ae91f39daa4653d7f8ebe55a154be032191bcb4390a75451708ee. The current image is locally present.
- CT108 live read-only evidence: /downloads/.tasks.json has five completed entries, SHA-256 27f8d654589a43d9664a132b177fee46f6ac1a88740ef5c8a80c900cb2a447c1; no MP4 queue .json files, but four large legacy MP4 files in the queue directory are preserved. No ffmpeg/yt-dlp/aria2 process was observed. Running _recover reads only .json jobs, and the worker filters completed/error states via mp4_recovery_hold_reason; auto_retry_monitor selects error statuses. These are observations, not a guarantee about the in-memory download queue. /api/tasks returned HTTP 401 without authentication; no authenticated session or introspection of the running in-memory queue was available.
- STARTUP_REPLAY_SAFETY=BLOCKED: although disk state and code support a low-risk hypothesis, current live in-memory task/queue state was not verified or coordinated with admission at cutover, so an accepted/racing job cannot be ruled out. Running code can update tasks on startup if statuses/fields differ and can delete matching .*.part.ts files; a current read found none. Settings have all default keys and version 3, so the examined migration logic would not currently rewrite settings. Do not infer safe restart from five completed disk records or zero JSON journals alone.
- Compose project/service missav-dlp-web uses eight inputs, including two /tmp files; all were readable. Rendering without the original invocation environment failed because TEDDY_LIBRARY_DELETE_DISCOVERY_WRITER_GID was missing and TEDDY_PUBLIC_ORIGIN unset. A read-only render using the actual running container's environment and group 988 succeeded: service image reference and declared environment values match; 14 mount destinations/source paths/modes match; restart policy and image default command agree. This partial comparison is not a preserved/validated full configuration and rollback procedure.
- ROLLBACK_READY=BLOCKED: old image exists, but no durable exact Compose/environment snapshot or verified rollback procedure and no safe restart/admission proof exists. Do not claim readiness based on image existence. Discovery DB read-only immutable connection returned 252 holdings (WAL was zero at inspection); Writer socket connection succeeded; Writer service and both Stage9 timers were active; generic wrapper uses --skip-media. These are point-in-time observations.
- One diagnostic mistakenly attempted to read every queue-directory file as JSON and the Python process was killed while encountering large MP4 files. It was read-only; subsequent bounded inspection did not reread media bytes. Afterward the container remained running with the same ID/start time, task/settings hashes matched the earlier read, and Writer/Stage9 units remained active. The kill cause and any transient memory pressure were not independently established.
- CANDIDATE_IMAGE=NOT_RUN; DEPLOY=BLOCKED; LIBRARY_API=NOT_RUN; WEB_UI=NOT_RUN. No image build, container replacement/restart, NAS/DB/Jellyfin write, forced job, settings edit, Writer/Stage9 change, backup movement/deletion or Stage11 change was performed. No candidate image ID exists.
- Next: obtain a normal authenticated live task view and a safe, coordinated method/evidence to rule out in-memory queued/in-flight work and concurrent admission at restart, and establish an exact durable Compose/environment snapshot and verified rollback plan. Repeat time-sensitive gates immediately before a separately continued deployment. Keep DLDLIB-001 IN_PROGRESS in all three workstreams; never alter queue/task state or bypass authentication to force a pass. Web UI remains unverified.

### EVIDENCE AND NEXT_DECISION

User approval 2026-10-28 KST; canonical pre-authorization base 30fd1fc7129c33c88beb421fc65ada3adbd6e425. The user's earlier running container, five completed tasks, empty MP4 queue, 252 holdings and HTTP 503 are historical observations, not current proof of restart safety. Proceed only after exact canonical authorization readback and fresh gates. Keep Governance, Downloader and Discovery Writer Safety IN_PROGRESS / DLDLIB-001 after this phase; restore original DLDWS-001 paired routes and Governance INACTIVE / NONE only during a later separate closeout following operational/UI verification.


## HISTORICAL CLOSED TEMPORARY TASK — DLDLIB-001 (2026-10-28)

### OBJECTIVE

Restore the Downloader web file manager's held-library listing with the user-approved minimum title-bound correction. The user explicitly approved temporarily switching Governance, Downloader and Discovery Writer Safety together from their original routing. DLDWS-001 is preserved, not completed or replaced.

### APPROVED_SCOPE

- Governance participation: temporary routing, approval/evidence records and canonical handoff only. Writer Safety participation: shared-routing consistency and Writer invariance only. Downloader owns the library product change.
- Complete and validate registration before product edits. Change only teddy_library_api.py MAX_TITLES from 250 to 500; if needed, update exactly one existing library smoke file. Prove 252 holdings list successfully and 501 remain blocked under the existing bound policy, using isolated fixtures and the existing related smoke.
- Publish scoped governance and product commits to canonical teddy-subtitle-stage11 by normal fast-forward, with exact remote readback. No contract change or new workstream is authorized or needed.

### PROHIBITED_SCOPE

No Docker image build/container replacement/restart, service/timer or Writer socket change, NAS/Jellyfin/operational DB/settings write, download/recovery execution, backup movement/deletion or policy change, Stage9 implementation/operation change, Stage11 change, refactoring, pagination, caching, authentication change, per-title exceptions, filter bypass, or other product behavior changes. Preserve query sorting/search, NAS inventory/path protection and other budgets, subtitle status, Jellyfin and permanent deletion behavior.

### ACCEPTANCE_CRITERIA

Registration preflight and governance structure PASS before coding; 252-item success and 501-item existing-policy rejection plus existing related library smoke PASS; git diff --check PASS; normal canonical fast-forward and exact remote readback. Code/test PASS is not production recovery. DEPLOY=NOT_RUN in this phase.

### EVIDENCE

- User-submitted CT108 diagnosis: missav-dlp-web, Discovery DB /discovery/teddy-discovery.sqlite3 accessible; jav/present=1 holdings=252; runtime MAX_TITLES=250; GET /api/library HTTP 503. Canonical read-only review confirms _build_items raises above MAX_TITLES and listing maps the exception to 503. These runtime observations were supplied by the user, not measured by this coding phase.
- Exact pre-transition canonical base: a7f90446094f6a703d88e5ebb3d3517a8a4ba2f7. Original router and three ACTIVE_WORK documents are recoverable byte-for-byte by that commit and these blob IDs:
- docs/governance/ACTIVE_WORK.md: Git blob 7791163613b2c647ffc16481c6704319d69b98a1
- docs/governance/governance/ACTIVE_WORK.md: Git blob cf424aeddf51775fb009499e125b8765e4f27f44
- docs/governance/downloader/ACTIVE_WORK.md: Git blob c02d122bbff3ff323f13bcb404caac985c68a40c
- docs/governance/discovery-writer-safety/ACTIVE_WORK.md: Git blob 4403afe868fc6847344d48aa95221880468a8f38
- Original live metadata: Governance INACTIVE / NONE, contract 1.0.1, requires governance; Downloader and Discovery Writer Safety IN_PROGRESS / DLDWS-001, contract 1.0.0, requires downloader,discovery-writer-safety. Stage9 IN_PROGRESS / STG9MEDIA-001 and Stage11 IN_PROGRESS / S11-WX011 remain unchanged.
- All original DLDWS-001 objectives, status/approvals, deployment/recovery evidence, candidates, Writer safeguards and backup preservation policy remain preserved below and at the exact pre-transition commit. Earlier live-task statements below are historical while this temporary task is active.

### DLDLIB-001 IMPLEMENTATION RESULT — 2026-10-28

- GOVERNANCE_REGISTRATION=PASS: registration commit b7f129b029b1a54eb63338633fb500ee69f6e63b was published by normal fast-forward and fetched back with exact SHA/tree equality before product edits.
- LIBRARY_FIX=PASS: the only product-code change is teddy_library_api.py MAX_TITLES 250 -> 500. All other NAS inventory budgets, path validation, listing/search/sort/subtitle/Jellyfin/deletion logic are unchanged.
- TESTS=PASS: the existing teddy_library_api_smoke.py now adds isolated real-SQLite/Flask API fixtures: 252 holdings HTTP 200 with 252 returned items; 501 holdings HTTP 503/library_unavailable before any NAS inventory call; fixture DB bytes unchanged by each request. The 252 test reproduced HTTP 503 before the constant change. Existing library API smoke and teddy_library_ui_smoke.py pass; git diff --check passes.
- Test runtime: system Python 3.13 with existing Flask dependencies from /tmp/dl001-py310-testenv-20261019/lib/python3.10/site-packages on PYTHONPATH; -B disables bytecode writes. Default Python lacked Flask and the old Python 3.10 environment lacked its standard library; no operational environment was installed or modified. All test DB/files/NAS/Jellyfin boundaries were isolated fixtures.
- DEPLOY=NOT_RUN; actual production API/UI recovery remains unverified. Governance, Downloader and Writer Safety stay IN_PROGRESS / DLDLIB-001 with the three-workstream requirement. Stage9 and Stage11 are unchanged; DLDWS-001 and backup preservation history remain intact.
- Next operational gate: obtain separate deployment authorization; freshly verify CT108 current image/source/Compose identity, the reviewed one-line product delta and rollback readiness, current task/queue state and Writer/dependency compatibility. Deploy only the authorized Downloader change, then verify authenticated GET /api/library and the web File Management library against current holdings. Do not force downloads/recovery, mutate NAS/DB/settings, or restore routing until the separately approved deployment/UI verification and closeout are complete.

### NEXT_DECISION

After code/test PASS, KEEP all three routes IN_PROGRESS / DLDLIB-001 with governance,downloader,discovery-writer-safety until a separately approved operational deployment and web UI verification are complete. This phase grants no deployment permission. Only a later explicit closeout restores the exact original Governance INACTIVE / NONE and DLDWS-001 paired routing above; never restore prematurely or discard DLDWS-001 history.


## JOINT DEPLOYMENT CLOSED — STG9MEDIA-001 (2026-10-28)

The user explicitly approved this closeout after submitting the missing representative operational evidence. The temporary four-workstream deployment overlay is CLOSED. The original independent routes are restored: Governance INACTIVE / NONE; Downloader and Discovery Writer Safety IN_PROGRESS / DLDWS-001 with their paired requirement; Stage9 IN_PROGRESS / STG9MEDIA-001 with stage9-media only. Stage11 is unchanged.

### APPROVED_SCOPE

Record the supplied evidence, close the temporary joint deployment, restore routing/required-workstream metadata, and update the canonical handoff. Preserve the original DLDWS-001 objective, approvals, deployment/recovery evidence, candidates and backup preservation policy. No backup-policy amendment or backup-cleanup task is registered in this closeout.

### PROHIBITED_SCOPE

No product source, runtime/service/timer configuration or restart, NAS/DB/Jellyfin write, forced download/metadata execution, backup transfer/deletion, Stage11 or Writer implementation change is authorized by this closeout.

### ACCEPTANCE_CRITERIA

The representative scheduled processing and actual NAS NFO/poster plus Jellyfin visibility evidence are recorded with correct attribution; original route/task/requirement sets are consistent; governance checks and diff check pass; the canonical branch is updated by normal fast-forward and read back exactly. Stage9 automatic operation and remaining independent work are preserved without a whole-product completion claim.

### EVIDENCE — USER-SUBMITTED CT108 MEASUREMENTS (2026-10-28 KST)

- The user submitted the operational measurements below; Codex did not execute the deployment, NAS checks, DB updates, or Jellyfin operations represented by them.
- PPPE-446: scheduled Stage9 processing COMPLETED; nfo_status=COMPLETE and poster_status=COMPLETE; NAS MP4 size comparison PASS; actual NAS NFO exists (769 bytes); actual poster.webp exists (11,010 bytes). jellyfin_notification_status=VISIBLE, jellyfin_recovery_status=VISIBLE, and media_jellyfin_visibility.status=VISIBLE; visible_at=2026-10-28T00:02:20+00:00; last_error=NULL and no media error.
- SNOS-403 and FNS-258: NFO/poster completion and Jellyfin VISIBLE confirmed by the user. Previously submitted operational logs confirm the dedicated timer is active, the generic Completion Runner uses --skip-media, and recent scheduled invocations completed with one media item and zero failures.
- Read-only canonical code review: teddy_discovery_media_filestation.py:_publish_one validates exact paths and input hashes, accepts an identical existing sidecar without rewriting it, rejects conflicting content/type, rechecks before create-only upload, handles concurrent creation as an error, and verifies final owner, size and SHA-256. _upload_create_only does not request overwrite and sets create_parents=false; publish_bundle restricts canonical sidecar filenames and only reads the video. This is a source review, not a new production permission or no-overwrite test.
- These measurements satisfy the bounded scheduled-run DB/NFO/poster/Jellyfin closeout evidence for the joint deployment. They do not establish whole-product completion, all-title quality, or resolution of every pending/retry/poster item.

Validation at closeout: all-workstream structure, restored DLDWS-001 paired preflight, independent STG9MEDIA-001 preflight, unchanged S11-WX011 preflight, governance smoke 21/21 and git diff --check PASS.

### NEXT_DECISION

Joint deployment coordination is closed. Continue the existing Stage9 automatic operation and independently registered Stage9 work within its existing approval boundaries; unresolved items are not declared complete. DLDWS-001 resumes its original paired routing and preserved approval/history; Governance is inactive. Any new feature, cleanup or operational mutation requires its own matching task authorization. All earlier joint deployment instructions below are retained as historical records and grant no renewed deployment authority.


## HISTORICAL CLOSED JOINT STAGE9 OPERATIONS AUTHORIZATION — 2026-10-27

Teddy explicitly approved local CT108 **root** execution for the dedicated Stage9 service on 2026-10-27, superseding only the previous *local non-root* service requirement. Stage9 NAS access MUST use existing non-admin `stage9_media` over verified HTTPS File Station, never administrator SSH. Prior joint operations records remain CLOSED historical evidence.

### APPROVED_SCOPE

- Temporarily route Governance, Downloader, Discovery Writer Safety, and Stage9 together as `STG9MEDIA-001`, preserving all DLDWS-001 and Stage11 work.
- Deploy the already-promoted immutable File Station Stage9 runtime, update only the generic wrapper to use existing `--skip-media`, retain the generic 60-second schedule/downloads/Organizer/metadata recovery, and install a separate Stage9 hourly randomized timer/service with max one item per run and Stage9-only failure-stop.
- Before production writes, confirm CT108 provenance and current service state, private credentials/CA, database integrity and backup, shared locks, NAS create-only sidecar rights, and a single-owner Stage9 scheduling path. Verify only one natural scheduled representative run and its DB/NFO/poster/Jellyfin effects; report no-work separately from actual publication.
- Local root preserves current root-only DB/WAL, Discovery read access, and shared title-lock semantics, without broad local ACL or ownership changes. NAS publisher remains least-privileged, with pinned TLS and existing no-overwrite protections.

### PROHIBITED_SCOPE

- No broad ACL laboratory or recursive chmod/chown, NAS administrator SSH publisher, TLS bypass, existing MP4/NFO/poster overwrite/delete, retry resets, bulk processing, new Stage9 code implementation, Writer socket changes, Stage11 work, or unrelated Downloader behavior changes. Stop if File Station Download 502 or actual JAV create-only permission remains unresolved.
- No full Downloader code refactoring until Stage9 is complete. After Stage9 and the separately planned four MP4 recovery items, review the full Downloader source read-only, report duplicates/structural issues, and obtain separate refactoring approval.

### EVIDENCE AND NEXT_DECISION

- Latest verified remote branch before registration: `3f159e175e4b2c915158b900e8e96a0ef9ddd792`; Stage9 skip-media smoke was previously repaired. CT108 generic timer `inactive/enabled` and old wrapper SHA `e49be466924287f328ea4d482b6a4806f0142cb4b8a71268c25bdb2365552b39` with no `--skip-media`; dedicated timer absent. Root-only directories and DB confirmed. Debian `acl` package installed, no permissions changed. All production Stage9 deployment and NAS/Jellyfin writes remain NOT_RUN.
- Proceed with narrow read-only live preflight. On completion or blocker, restore original routes (Governance `INACTIVE/NONE`, Downloader and Writer `DLDWS-001` with paired requirements, Stage9 `STG9MEDIA-001` alone), preserving Stage11.

## OBJECTIVE

Record the user's approved personal-use, right-sized development and validation priority in the canonical common contract and AGENTS.md; close GOV-008 after exact readback.

## APPROVED_SCOPE

- Edit only AGENTS.md and common contract, with minimum routing/active-work metadata needed for GOV-008 activation, version alignment, and closure.
- Prioritize practical personal use; retain existing files' no-delete/no-overwrite safeguards, scoped paths, and fail-closed behavior; avoid disproportionate validation tooling.

## PROHIBITED_SCOPE

- No product, Stage9, Stage11, Downloader, Writer Safety, NAS, DB, Jellyfin, account, timer, or service changes.
- No weakening existing data protection or authorization rules; no claimed runtime validation.

## ACCEPTANCE_CRITERIA

- Approved principle appears in both AGENTS.md and the common contract with consistent version and routing metadata.
- Existing independent workstream states and contracts remain unchanged.
- Canonical branch fast-forward and exact readback, then Governance restored to INACTIVE / NONE.

## EVIDENCE

- GOV-008 CLOSED after exact remote readback; common project contract updated to v1.0.1 and AGENTS.md updated with personal-use development priorities, minimal validation, and retained essential no-overwrite/fail-closed safeguards.
- Policy commit: 61d38019e746b4c0e079b302f9a9089ac21e7faa. Canonical branch: teddy-subtitle-stage11.
- Validation: four updated policy/metadata files exactly read back; existing Stage9, Stage11, Downloader and Writer Safety task routes unchanged; no runtime/product/NAS/DB/service changes.
- User explicitly approved GOV-008 in chat on 2026-10-27 KST.
- Activation base 77b3c388c2e31d311321883001c86200d3482e6d on teddy-subtitle-stage11.
- Product and runtime modifications are outside this approval.

## NEXT_DECISION

GOV-008 is CLOSED; Governance is INACTIVE / NONE. Stage9 remains a separate approved task; any future governance policy change needs its own approval.

## PREVIOUS GOVERNANCE RECORD (PRESERVED)

## OBJECTIVE

Close the temporary joint Stage9 integrated transition at the NAS least-privilege access gate, record the verified reason, and restore the original workstream routing. No operational changes were made.

## APPROVED_SCOPE

- Restore Governance to `INACTIVE / NONE`, Downloader and Discovery Writer Safety to `IN_PROGRESS / DLDWS-001` with their original required-workstream pair, and Stage9 to `IN_PROGRESS / STG9MEDIA-001` with its original single-workstream requirement.
- Preserve the joint activation and the Stage9/DLDWS evidence, record the NAS access blocker, and verify restored routes and protected Stage11 status.

## PROHIBITED_SCOPE

- No further operational or product changes are authorized by this closed Governance activation.
- No NAS account, ACL, credential, file, CT108 account, wrapper, service, timer, release, database, Jellyfin state, Downloader behavior, Writer socket, or Stage11 data was changed.
- No contract, validator, or shared project policy was changed.

## ACCEPTANCE_CRITERIA

- The one-time joint registration is recorded and its exact canonical activation readback is verified.
- All original routes are restored and the Stage11 `S11-WX011` route remains unchanged.
- The unresolved NAS authentication/least-privilege prerequisite is accurately recorded; no operational mutation is claimed.

## EVIDENCE

- User approved this integrated transition on 2026-10-26 KST. Activation base and freshly read remote `teddy-subtitle-stage11` SHA: `9c89efe29c5b9af7b5cc70aff305738a9723d2c2`.
- Existing promotion `43fa8c034d4c6198507a2e7138829b6f3f6cfc15`, Stage9 offline verification, and prior operational observations are evidence only; no prior blocked step is treated as passed/current without revalidation.
- Activation commit `ac61cd8df99f98aa7f678f4684b08836d9177e9e` was posted as a fast-forward and all five documents were exactly read back before live inspection.
- Read-only CT108 check confirmed host `downloader`, `uid=0(root)`, PID 1 `systemd`; generic timer `inactive/enabled`, 60-second schedule, static service `inactive`, root execution, wrapper SHA-256 `e49be466924287f328ea4d482b6a4806f0142cb4b8a71268c25bdb2365552b39`, and no `--skip-media`.
- DSM was `7.2.2-72806 Update 4`; official DSM terminal policy limits SSH/Telnet login to local administrators. Existing SSH identity is `ssikgun` in `administrators`, and the exact Stage9 library root is mode `777`; its current ACL contains only existing principals and no Stage9 publisher. `GANA-3223` directory was absent.
- Unauthenticated DSM API Info GET over HTTP reported File Station Info v2, Upload v3, CheckPermission v3, MD5 v2, and CopyMove v3. HTTPS port 5001 failed system trust with an untrusted issuer. Existing SSH identity has no noninteractive sudo; therefore no trusted authenticated DSM provisioning/API route for a new non-admin File Station principal was available. Do not send DSM credentials over HTTP or reuse the administrator key in the runtime.
- The least-privilege publisher gate failed. No NAS account/ACL/credential, CT108 account/permission, product source, runner/wrapper, systemd unit/timer, release, DB/backup, NAS file, or Jellyfin state was changed. DLDWS-001 and S11-WX011 were not modified.
- Restored route validation and exact remote readback are recorded at this closure; operational access and deployment remain blocked.

## NEXT_DECISION

Governance is inactive. The Stage9 integrated transition cannot resume until a supported authenticated DSM provisioning path and trusted TLS authority are available for a non-admin, path-limited File Station publisher. No operational authority remains from this closed joint registration.

## HISTORICAL CLOSED GOVERNANCE RECORDS

All pre-existing closure and GOV-007 evidence below remains historical and unaltered; it does not override this current task while this joint registration is active.

- ## CLOSED JOINT OPERATIONS AUTHORIZATION — STG9MEDIA-001 (2026-10-26)

The user explicitly re-authorized the unfinished integrated Stage9 cutover on 2026-10-26 after direct Codex execution-environment verification established access to CT108. This reopens only the exact joint task below; the previous closure remains preserved in the parent commit and is not treated as continuing authority by itself.

### APPROVED_SCOPE
- Create a dedicated non-login, non-root Stage9 system account and grant only the verified minimum DB, lock, SSH credential, Jellyfin credential, and runtime access required by the promoted Stage9 runner.
- Use the already promoted canonical --skip-media Completion Runner path to preserve the existing 60-second Downloader schedule and its existing download, Organizer, and metadata-recovery behavior while removing Stage9 Media work from that path.
- Install an immutable Stage9 release from already promoted source 43fa8c034d4c6198507a2e7138829b6f3f6cfc15; install and activate only the dedicated Stage9 service/timer and its Stage9-only failure stop.
- Create a fresh Stage9 DB backup only if required by the validated transition, verify integrity and an isolated copy, then observe at most one item per scheduled Stage9 invocation. Existing GANA-3223 is not to be reprocessed.
- Verify one normal scheduled run, preserve NFO/poster/video no-overwrite behavior, bounded retry/lock/Jellyfin policies, and the generic Downloader path; restore the original workstream routing at closeout.

### PROHIBITED_SCOPE
- No root execution for the dedicated Stage9 service, broad recursive ownership or mode changes, credentials in logs/Git/environment examples, NAS-wide permission grants, or permission expansion beyond exact verified paths.
- No download or MP4 policy changes, forced Downloader/Organizer runs, Writer socket source/service changes, Stage11 changes, other service/timer changes, product-source reimplementation, or unapproved job/file changes.
- No database initialization, legacy-state/retry reset, automatic backup restore, forced termination of publication, existing NAS artifact replacement, bulk processing, or Jellyfin actions beyond the promoted bounded implementation.
- Stop if minimum privileges, remote SSH publish scope, concurrent-writer safety, live data integrity, or timer separation cannot be proven.

### ACCEPTANCE_CRITERIA
- The four selected routes and active-work files authorize exactly STG9MEDIA-001 with the complete required-workstream set and approved contract versions.
- Dedicated service runs only as the dedicated non-root account, with verified path-limited access; the old generic timer continues its 60-second schedule with --skip-media.
- No two active schedules can process Stage9 Media; the new hourly timer has its bounded limits and failure-stop behavior.
- The first observed scheduled run is recorded separately from a successful artifact lifecycle; no unsafe DB, NAS, Jellyfin, Downloader, Writer, or Stage11 change occurs.
- After success or safe stop, Governance, Downloader, Discovery Writer Safety, Stage9, and Stage11 are left in their authorized final routing states and the remote readback is exact.

### EVIDENCE
- User approval received 2026-10-26 KST. Activation base and current remote SHA: 2cc70990460e79eb2e128a1efdcb1846905ae324.
- The already promoted product change is 43fa8c034d4c6198507a2e7138829b6f3f6cfc15; it will not be reimplemented or re-promoted.
- Previous joint task closure and its evidence remain in canonical history at parent 2cc70990460e79eb2e128a1efdcb1846905ae324.
- Direct authorized CT108 preflight confirmed hostname `downloader`, root operator, PID 1 `systemd`, and the existing Runner SHA-256 `e49be466924287f328ea4d482b6a4806f0142cb4b8a71268c25bdb2365552b39`. The existing generic timer remains inactive/enabled and its wrapper has no `--skip-media`.
- The cutover stopped before operational writes because the existing NAS SSH identity is `ssikgun` with the `administrators` group and verified writable access to `/volume1/video`, `/volume1/video/video2`, and `/volume1/video/video2/JAV`; the approved minimum-permission condition is not met. No restricted publisher credential was available or created.
- SQLite was opened with `mode=ro` and `PRAGMA query_only=ON`: integrity was `ok`; 119 jobs were present (109 COMPLETED, 8 FAILED, 2 PENDING, 0 RUNNING), max attempt count 17161, and 109 visibility rows. No DDL/DML was issued. The main DB size/mtime and WAL mtime remained unchanged; SQLite updated the existing SHM file mtime/ctime during the read connection, so SHM metadata side effect is recorded.
- No service account, ACL, wrapper, service, timer, release, backup, NAS artifact, Jellyfin state, or product source was changed. Activation commit `cff602a261a79f0dce7bc31ed445dd05ded2814f` was read back exactly from the canonical branch before the preflight.

### NEXT_DECISION AT ACTIVATION (SUPERSEDED BY CLOSURE)
- Keep this joint task active until the first scheduled Stage9 run is verified or a safety gate forces a documented stop; then close it and restore the original routing.

- The prior Governance closure record is retained in the parent commit at `2cc70990460e79eb2e128a1efdcb1846905ae324`; historical GOV-007 evidence remains below.

## NEXT_DECISION

Before another operating attempt, provide and explicitly authorize a Stage9 NAS identity whose remote command and write scope are constrained to the metadata publisher and the verified library sidecar paths. Do not reuse the current administrators-group SSH identity for the non-root service.

## HISTORICAL GOV-007 (CLOSED)

The following record is retained from the prior closed GOV-007 task. It is historical evidence only and grants no current authorization.

### GOV-007 OBJECTIVE (CLOSED HISTORY)

GOV-007 completed the approved independent Stage9 Media governance registration and is closed after exact canonical remote readback. No Governance task is currently active.

### GOV-007 APPROVED_SCOPE (CLOSED HISTORY)

- Register the `stage9-media` workstream with its approved v1.0.0 design contract, independent router entry, and `INACTIVE / NONE` active-work record.
- Record `STG9-MEDIA-001` only as a proposed, unapproved identifier; Stage9 implementation remains unauthorized and inactive.
- Route Stage9 Media metadata/NFO/poster/Jellyfin item-state behavior away from the generic Downloader area while preserving Downloader `DLDWS-001`, Discovery Writer Safety `DLDWS-001`, and Stage11 `S11-WX011`.
- Restore Governance to `INACTIVE / NONE` after exact canonical readback of the separate Stage9 registration commit.

### GOV-007 PROHIBITED_SCOPE (CLOSED HISTORY)

- This completed registration authorizes no product code or test edits/runs, Docker builds, deployment, runtime release or service changes, or operational data changes.
- No production DB, NAS, Jellyfin, download/retry/recovery, Writer socket, or Stage11 data writes or mutations.
- Do not change the common contract or existing Downloader, Discovery Writer Safety, or Stage11 contracts, active tasks, IDs, or evidence.
- Do not treat `STG9-MEDIA-001` as active; stop before Stage9 implementation until a separate user-approved task is registered with a validator-compatible ID.

### GOV-007 ACCEPTANCE_CRITERIA (CLOSED HISTORY)

- Governance router and active-work record show `INACTIVE / NONE`, version 1.0.0, and `REQUIRES_WORKSTREAMS: governance`.
- The canonical Stage9 registration commit is read back by exact SHA and contains the v1.0.0 approved contract, Stage9 `INACTIVE / NONE`, and the independent `stage9-media` route.
- The proposed `STG9-MEDIA-001` remains unapproved; current task-ID validation rejects that two-hyphen form, and no validation policy was changed.
- Downloader and Discovery Writer Safety remain `IN_PROGRESS / DLDWS-001` with `REQUIRES_WORKSTREAMS: downloader,discovery-writer-safety`; Stage11 remains `IN_PROGRESS / S11-WX011`.
- All-workstreams structure, governance smoke, existing task preflights, expected Governance rejection after closure, and `git diff --check` pass.
- Only governance documents changed; no product or operational changes occurred.

### GOV-007 EVIDENCE (CLOSED HISTORY)

- The user explicitly approved Governance activation and Stage9 Media governance registration on 2026-10-25. Verified canonical base: `e6e1a12eee6c8adfdb6bf09cdfe15ece34b6d515` on `teddy-subtitle-stage11`.
- Governance activation commit `5aed5316fbef0d6105fd0fd93798e322724522cd` was published by normal fast-forward from the verified base and read back as the exact canonical branch SHA. GOV-007 preflight passed during the active phase.
- Separate Stage9 registration commit `b28729e675232345825866caca3b455fc6484e51` was published by normal fast-forward from activation commit `5aed5316fbef0d6105fd0fd93798e322724522cd`. `git ls-remote` and the refreshed remote-tracking ref both reported the exact registration SHA; `git diff --exit-code` confirmed the fetched canonical tree matches it.
- Canonical readback confirmed the Stage9 contract and active-work paths, approved contract version 1.0.0, `stage9-media` router entry, and Stage9 `INACTIVE / NONE`. Downloader and Discovery Writer Safety remain `IN_PROGRESS / DLDWS-001`; Stage11 remains `IN_PROGRESS / S11-WX011`.
- GOV-007 is closed only after exact registration readback. No task-ID validator or common-contract policy was modified. `STG9-MEDIA-001` remains a proposal and is not runnable under the current one-hyphen task-ID format.
- Baseline and registration all-workstreams governance structure passed; governance smoke passed 21/21; DLDWS-001 and S11-WX011 preflights passed. GOV-007 preflight passed while active and is expected to reject after this closure.
- The previous DLDWS-001 registration evidence and archived pre-registration records remain preserved at `docs/governance/history/DLDWS-001-registration-base-34dede0/`; the existing workstream records and common contract were not modified.
- This registration and closure changed governance documents only. No product source, product tests, Docker build, runtime service, download, database, NAS, Jellyfin, or user data was changed.

### GOV-007 NEXT_DECISION (AT CLOSURE)

No Governance task is active. Before Stage9 implementation can be considered, the user must decide whether to separately approve a validator-compatible task ID or a Governance validation change for `STG9-MEDIA-001`, then approve the exact implementation and offline-verification scope. Production writes require additional explicit authorization.
