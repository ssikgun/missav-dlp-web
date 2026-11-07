# P08LIB-001 — Mobile Library DB status card layout (2026-11-07 KST)

Repository: `ssikgun/missav-dlp-web`
Canonical branch: `teddy-subtitle-stage11`
Source commit: `a774175cc80a122f3c388bb5f034502c00feaff1`
Status: **SOURCE_ONLY / GITHUB_READBACK_PASS / PRODUCTION_NOT_DEPLOYED**

## User approval and exact scope
Following iPhone screenshots of the deployed File Management dashboard, Teddy approved the proposed minimal CSS-only change: make only the three "라이브러리 DB 현황" NAS holdings status cards stack as single-column, full-width cards on narrow mobile screens. Preserve existing desktop dashboard, "보유 라이브러리" five-card mobile grid, Stage12 task metrics, business/API semantics, all data and background services.

## Implementation and verification
- Modified exactly `templates/teddy-library.css`; appended an `@media (max-width: 720px)` rule for `#file-management-view-subtitle-status .library-db-status { grid-template-columns: minmax(0, 1fr); }`.
- Existing shared `.library-summary-cards, .library-db-status` desktop rule and preexisting 1020/720/420px breakpoints left untouched.
- GitHub readback on the exact branch: PASS; commit diff contains only this CSS file; new blob `1f76d941ea6ab55164c6a5672527c48a65e5ef7d`.
- Static CSS selector/breakpoint checks: PASS. Full Docker build, production runtime visual test of this **new** CSS, and live mobile acceptance: NOT RUN.
- Preceding deployed layout was already visible on PC/iPhone; unauthenticated endpoint protections and authenticated `/api/library`, `/api/subtitles/status` JSON 200 checks had passed. These checks refer to the **previous deployed artifact**, not this new source-only patch.

## Protected production baseline and next gate
- Last user-confirmed live Downloader image: `sha256:ebd164d631450660b79ca29141a3b8c317f71df443b2d209feec51a8a35c000a`.
- Prior actual container replacement succeeded; `LIVE_ENV_PARITY=PASS`, no restart, HTTP auth boundary PASS, Stage9 timer active.
- Preserve rollback directory `/opt/missav-dlp-web/backups/p08lib-db-ui-deploy-20261107-xtxqy4pv`, earlier images/backups, Stage9/Writer/Stage11, NAS/DB/Jellyfin, and protected worktrees.
- **NO** new Docker build, image promotion, redeploy, rollback, job retry, data write, or cleanup was executed for this mobile CSS correction.
- Next: if Teddy separately authorizes another build/production deploy, perform fresh active-task/governance preflight, exact-image build and single-service promotion with protection gates, then inspect a real iPhone screenshot for one-column DB cards. Do not infer production authorization from this source approval.

This checkpoint is additional source history; the repository's existing `CURRENT_HANDOFF.md` is unchanged.
