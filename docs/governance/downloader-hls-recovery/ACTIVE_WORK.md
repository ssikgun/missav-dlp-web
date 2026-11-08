# Downloader HLS incident recovery — active work

## 2026-11-08 17:02 KST — DLHLS-001 SORA-489 read-only recovery checks (CURRENT EVIDENCE)

- CT108 live console output establishes error states for exactly three safety jobs, all HLS semantic-plan mismatches: `cba0fdda-7f00-460e-b722-fa3e8a78681e` (1323/2061 TS), `be88eb5a-cecd-4aee-8637-d6e16141b394` (72/2088 TS), `4adb423e-5be0-4560-b113-3eef5df6f19b` (0/2118 TS). Manifest completion counts equal actual TS files, total 1395. The initial script mistakenly required `status == "에러"`, while live statuses start `"에러: 저장 공간/잠금 보호: ..."`; the narrower check was fixed in subsequent read-only reports.
- Candidate: `4adb423e-5be0-4560-b113-3eef5df6f19b`, SORA-489, `missav123.com/dm4/ko/sora-489` (query withheld), `storage_folder=missav`. No other task with exactly the same URL, no locally enumerated filename containing `sora-489`; candidate task has no `filename`, `local_result_path`, or `local_result_paths`. Exact output name, final destination/NAS collision, and live source viability remain NOT_VERIFIED.
- Current CT108 read-only storage: free 36.58 GiB, reserve 4.89 GiB, available after reserve 31.68 GiB; zero active/other tasks, zero host FFmpeg processes, Downloader container running with zero restarts and correct work mount. Candidate recorded size estimate UNKNOWN.
- 2118 candidate segments. Two cross-title reference samples imply **rough and non-binding** candidate sizes 3.76 GiB (1323 TS totaling 2.35 GiB) and 5.77 GiB (72 TS totaling 0.20 GiB); not a reliable upper bound. The checked-in safety code calculates conservative remux copy output as input + max(input/10,64 MiB); this is product-code context, not an E2E guarantee.
- `CHECK=PASS` is limited to these offline/read-only observations. `FULL_REQUIRED_SPACE=CONFIRM_NEEDED`, `OUTPUT_COLLISION=NOT_VERIFIED`, `SOURCE_FETCH=NOT_RUN`, `DOWNLOAD=NOT_RUN`, `RETRY=NOT_RUN`, `DEPLOY=NOT_RUN`, `NAS_WRITE=0`. No existing task or 1395 TS files were changed by the read-only commands.
- Next: one small read-only local/final-destination inspection, then decide an operator go/no-go with explicit source/network and remaining capacity/ownership gates. Do not treat the reference estimates as clearance or bypass the semantic-plan mismatch.

WORKSTREAM: downloader-hls-recovery
TASK_ID: DLHLS-001
STATUS: IN_PROGRESS
CONTRACT_VERSION: 1.0.0
REQUIRES_WORKSTREAMS: downloader-hls-recovery

## OBJECTIVE

Safely investigate the three 2026-11-07 failed HLS jobs and prepare no more than one isolated, new-identity recovery trial without loss of 1,395 TS fragments or the existing P08LIB-001 UI task.

## APPROVED_SCOPE

- Teddy approved independent DLHLS-001 scope and conflict-free GitHub routing on 2026-11-08.
- Perform bounded read-only CT108 checks on original job identities, parts/manifests, busy workers/remux, current disk required+reserve, source identity, output ownership/no-collision and a zero-TS candidate.
- Plan at most one new-identity representative recovery test. Before any network/write, verify free >= required + reserve, source/output safety, original artifacts, and explicit operator go/no-go.
- Preserve P08LIB-001 shared task unchanged and keep UI deployment on HOLD; record important checkpoints in the canonical handoff.

## PROHIBITED_SCOPE

- No immediate live download just because routing passes, no old retry-button replay, simultaneous three-job retry, changed playlist-plan hash bypass, or old TS mixing.
- No deletion/overwrite of originals, jobs, manifests, .parts, TS, backups/cache, existing outputs, NAS/Jellyfin, Stage9, Writer, Stage11 or protected checkout.
- No general Downloader code/queue edit, Docker build/deployment, UI promotion, change to global MP4 concurrency or reserve policy without separate explicit approval.

## ACCEPTANCE_CRITERIA

- Canonical GitHub has a separate `downloader-hls-recovery / DLHLS-001 / IN_PROGRESS` route, v1.0.0 approved contract, and self-only required workstreams; all existing P08LIB-001 four-way UI entries and S11-WX011 remain unchanged.
- Current governance structural check and task-specific preflight accept this new route; unrelated task IDs still fail closed. GitHub updates are normal fast-forward with remote readback.
- Before any trial, a fresh bounded read-only CT108 check proves identity, no collision, required+reserve and no competing workers and records operator go/no-go; original 1,395 TS and jobs remain untouched.

## EVIDENCE

- User approved independent recovery scope and routing change on 2026-11-08. GitHub base `50df59b66de50e19e9e7c91dfeeb4527901fc9ce` records read-only basic preflight: three failed jobs, zero active, fragments 1323+72+0, 36.61 GiB free, running Docker container, zero restarts.
- These observations do not show required+reserve capacity or destination/source safety. Build disk-pressure contribution is plausible, not proven. Changed HLS plan SHA mismatch remains unresolved.
- Registration performs no actual retry, job write, Docker deploy, NAS change or product edit.

## NEXT_DECISION

Confirm exact remote task route/readback, then only one new read-only CT108 capacity/worker/output preflight before the operator go/no-go decision on the zero-TS trial.
