# Downloader SpoofDPI headless startup contract

CONTRACT_VERSION: 1.0.0
PROJECT_CONTRACT_STATUS: APPROVED
APPLIES_TO: DLSPD-001, Teddy-approved 2026-11-10 exact headless startup repair and conditional missav-dlp-web-only image release.

## Purpose and precedence

- Repair the demonstrated bundled SpoofDPI v1.5.5 failure `failed to start tui: could not open a new TTY: open /dev/tty: no such device or address`. Current `teddy_spoofdpi.py` launches `spoofdpi` with no flags and exits code 1 before serving 127.0.0.1:8080. Installed `--version` and `--help` confirmed v1.5.5 and `--no-tui` support.
- This separate workstream owns only the SpoofDPI startup argv, proportional offline safety test and image-only Downloader rollout. It takes narrow precedence over general downloader's held P08LIB-001 UI work for this exact shared startup file/operational replacement; no other source or runtime policy transfers here.
- The completed fresh-ID retry API remains DLFR-001. The original three failed jobs, 1,395 TS and single SORA-489 live trial remain DLHLS-001 and must not be started by this task.

## Allowed changes

- Change exactly the SpoofDPI startup argv from `["spoofdpi"]` to `["spoofdpi", "--no-tui"]` in `teddy_spoofdpi.py`, with at most a matching documentation/comment correction and one focused offline regression smoke. Preserve the existing two-second process/error diagnostics, executable, default HTTP localhost:8080, and proxy/VPN fallback semantics.
- Build one small offline candidate image based on the exact current running image with only the verified SpoofDPI startup module overlaid; do not rebuild the entire dirty/newer GitHub source or include held P08LIB-001 UI. Preserve the DLFR-001 API, image runtime config, four held UI hashes, and all prior images.
- Teddy explicitly authorized both preparation and actual target-only service replacement on 2026-11-10, **conditional** on fresh protected idle/no active download/remux checks, no competing Docker build, disk reserve and image-build headroom, an old-image rollback point, exact effective 13-file Compose settings with an image-only override, and pre/post-change service/data/other-container checks. Use the existing approved Downloader-only maintenance-stop method during the image build.
- A failed/unknown gate aborts further steps with current state reported. No automatic retry/rollback; manual rollback must be backed by exact previous image and verified original Compose inputs.

## Prohibitions

- No change to application extraction logic, downloader network routing, download queues/HLS/MP4, storage/ownership/collision/reservations, authentication, UI HTML/CSS/JS, shared source manifests beyond this exact startup fix, or other services.
- No direct edits of the running container, no implicit source pull, image prune, deletion, old-image overwrite, NAS/DB/Jellyfin/Stage9/Writer/Stage11 mutation, protected dirty worktree edits, media download, source-page GET or live retry.
- Never mix or delete the failed original three HLS records/parts/playlist plans or 1,395 protected TS. Restoring SpoofDPI is **not** approval for DLHLS-001 to bypass current source, output identity, full required+reserve and worker gates.

## Acceptance and next decision

- New self-only router/contract/active work registration and selected governance validator checks PASS without changing other workstreams.
- Candidate byte/hash and narrow argv/offline mock regression PASS, with actual binary headless support already checked. Product runtime PASS only after single-service image cutover and local 127.0.0.1:8080 listener/process health observed without starting a video download.
- Observe protected original jobs/TS counts, existing UI/source/API hashes, config/port/mount/network/env and other container identity parity. Any uncertain result stops at its observed stage and retains rollback.
- After startup restoration, return to DLHLS-001 read-only SORA-489 source/size/ownership gates; do not issue a real fresh retry POST under DLSPD-001.
