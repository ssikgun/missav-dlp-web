# Governance workstream — active work

WORKSTREAM: governance
TASK_ID: GOV-001
STATUS: READY_FOR_USER_REVIEW
CONTRACT_VERSION: 1.0.0
REQUIRES_WORKSTREAMS: governance

## OBJECTIVE

Build and validate the first Downloader governance candidate from the user's GOV-001 authorization, leaving common and Stage11 contract candidates in draft state for user review.

## APPROVED_SCOPE

- Add shared repository instructions, the common contract, the workstream routing registry, and workstream-specific active-work records.
- Add the Stage11-only contract and workstream-aware ChatGPT startup instructions.
- Add a standard-library offline preflight supporting explicit one- or multi-workstream selection and fail-closed validation.
- Add smoke coverage for authorization, version alignment, Stage11 isolation, unrelated workstream independence, and shared-workstream contract checks.
- Add a governance-only GitHub Actions workflow. Do not change branch protection or deployment workflows.
- Record only the GOV-001 candidate and review status in the existing canonical handoff, using a separate docs-only commit.
- Work from `teddy-subtitle-stage11` HEAD `634948fb85ee3ac14300596d77dae223968183e9` in an isolated worktree; push the candidate and separately authorized handoff update.
- Read and preserve `/root/.codex/AGENTS.md`; make no global instruction changes.

## PROHIBITED_SCOPE

- Any Stage11/Stage12 subtitle feature development or refactor, or any unrelated Downloader product-code change.
- Any Hermes, Whisper, ASR, or other model execution.
- Any production database, queue, service, timer, NAS, Jellyfin, subtitle, deployment, or publication write.
- Any change to `/root/.codex/AGENTS.md`, the protected dirty worktree, Docker/deployment workflows, branch protection, or final contract approval state.
- Any user-unapproved workstream registration, design resolution, new task, or automatic next development step.

## ACCEPTANCE_CRITERIA

- Root `AGENTS.md` and the common project contract contain only shared Downloader workstream rules; Stage11 design goals and policies exist only in the Stage11 contract.
- The root active-work file routes separate workstreams. Stage11 is paused without blocking an independent registered workstream; GOV-001 is active only in governance.
- Stage11 preflight requires the Stage11 contract. Supplying only the common/unrelated contract fails.
- Preflight supports repeated `--workstream` selections; shared work requires every declared related workstream and verifies each contract, active task, and matching task ID.
- Preflight fails for an unregistered workstream, unauthorized task ID, paused selected workstream, missing file/section, invalid contract metadata, version mismatch, or multiple active task IDs in a workstream.
- Smoke tests pass for valid GOV-001; nonexistent and P2-N IDs; contract version mismatch; missing contract; missing acceptance criteria; multiple active tasks; invalid contract status; Stage11's required contract; unrelated work while Stage11 is paused; shared workstream coverage; and unregistered workstream.
- Both project contracts remain `DRAFT_PENDING_USER_APPROVAL`; the candidate is committed/pushed on `codex-governance-gov001-20261014`, and the canonical handoff receives a separate docs-only commit/push. The candidate is not merged into the canonical branch.
- Global instructions and protected dirty worktree remain unchanged. Report technical governance PASS separately from subtitle product-quality status.
- Session instruction application is not reported PASS without a separate harmless session test; if unavailable, report `SESSION_INSTRUCTION_TEST=NOT_RUN` and give a manual `/new` check.

## EVIDENCE

- Source branch fetched from origin at `634948fb85ee3ac14300596d77dae223968183e9`.
- Existing handoff, frozen Stage11 design/roadmap, Normal Mode record, source tree, README baseline, and three existing GitHub Actions workflows were audited before writing.
- Global instruction SHA-256 before work: `6aaa9bd37818c6ff8409c129efa7396bc655ca3cfb5cfbbc09086e823711b6ff`.
- Workstream routing and contract selection are covered by the offline smoke suite; final push and CI evidence will be recorded in the canonical GOV-001 handoff entry.

## NEXT_DECISION

User reviews the common contract, Stage11 contract, and ChatGPT startup instructions, then approves or requests changes. Do not select or begin the next subtitle task until the user does so.
