# Stage11 Normal Mode — 2026-10-12

`STAGE11_NORMAL_MODE=PASS`, `USER_INTERVENTION=0`.
Two actual native translations completed, source/output protection passed, and
the deployed native queue completed its first corrected production cycle with
a safe, recorded invalid-JA error. This does not claim successful new NAS
publication, processing of the entire backlog, or perfect dialogue recognition.

The existing source parser, SubtitleCat selector, affine acceptance policy,
model-input normalization, cue identity, source-aware output guards, absorption
validator/materializer, SSH bridge, Stage12 state machine/title lock/publisher
and UI heartbeat are reused. Necessary boundary/absorption/whole-title helpers
were taken from the existing boundary worktree without editing it. Optional
supplemental research code, GPU Worker changes and new models are excluded.

Normal Mode separates the external-JA translation from optional missing dialogue
recovery. It requires source-bound baseline evidence and accepted external JA;
missing JA/unresolved timing/core Hermes failure exits with a durable reason.
It performs fresh isolated Hermes native chat with the previously established
zero-tool config and the existing provider/model/reasoning. Whole-title and
fixed-64 fallback share strict identity, absorption and source-aware text guards.
Every turn retains the existing 600/3600-second limits and two validation
attempts. No subtitle listening, Japanese checking, manual editing or approval
is requested. Automatic missing-dialogue insertion remains disabled. Only clear
source metadata is omitted; awkward or uncertain dialogue is retained.

| Title | JA | New KO | Absorption | Metadata omitted | Native Hermes calls |
| --- | ---: | ---: | ---: | ---: | ---: |
| FNS-247 | 313 | 300 | 13 | 0 | 1 |
| JUR-750 | 661 | 648 | 11 | 2 | 1 |

Real NAS videos and source size/mtime were verified. Existing baseline ASR and
retained external JA were reused; both live SubtitleCat fetch/selection paths
subsequently returned ACCEPT_HYBRID with exactly the same JA SHA. Native raw
stdout/stderr, runtime session receipts, authoritative/model inputs, source
proof, output and failures remain under the server artifact roots. The evidence
folder contains summaries and hashes rather than subtitle text.

Final SRTs:

- `/opt/missav-dlp-web/discovery/stage11-normal-e2e-20261012/artifacts/FNS-247/clean-ko-v1.srt`
  SHA `55c5a92a3857e2e79de4a10a37aa728c112c12a9a75f491b2c7a6c66da68a58d`
- `/opt/missav-dlp-web/discovery/stage11-normal-e2e-20261012/artifacts/JUR-750/clean-ko-v1.srt`
  SHA `d25d276c78efabb67dc334b325bf8e0fdd1a56b653d0a725aecd89c088feda56`

Both pass canonical SRT readback, time order, original cue/source-index coverage,
absorption unions, exact duplicate checks and actual Stage12 artifact-bundle
preflight. Existing KO inventory is protected/UNRESOLVED for both titles; these
comparison outputs do not replace existing NAS subtitles or refresh Jellyfin.
New eligible jobs use the existing Stage12 no-overwrite publication contract.

The historical FNS-247 JA313/KO296/absorption17 result and SRT remain byte/SHA
identical. All 2,213 original protected pins matched. New output counts are model
results and are never production constants or general expected values.
Saved native supplemental AMBIGUOUS13 decisions were replayed with their original
strict parser: approved0, eligible0. Negative moan/music/hallucination evidence is
retained; it has not established safe automatic insertion. Normal Mode skips
this feature and continues the primary translation.

The first FNS execution exposed a result-readback field access bug after a valid
Hermes response and SRT were already saved. The generic reconstruction was fixed
(candidate title comes from the source snapshot; route fields use named
arguments; JSON tuple/list comparisons use canonical wire bytes). A native
resume reused the immutable result, made zero further model calls and completed.
The original failure log is retained. GVH-713 has valid text but fails the
unchanged timing acceptance policy with UNRESOLVED; it exits automatically with
no Korean artifact, user request or model call. Offline tests cover no JA,
Hermes failure/timeout, malformed identity, bounded retries, immutable readback,
source-aware runaway rejection and fixed-64 fallback.

Validation: 11 focused offline tests, 18 existing Stage11/Stage12/title-lock smoke scripts,
Python compile, shell syntax, systemd unit verification and diff check PASS.
Synthetic/offline results are distinguished from the two actual model runs.
Exact Japanese transcription accuracy and semantic perfection are unmeasured;
no claim of complete dialogue recovery is made.

The new timer/queue wrapper admits at most four unseen canonical holdings and
runs one existing PENDING job per cycle. It preserves all historical states and
existing KO; it does not reset failed rows or enable forensic approval paths.
Deployment/rollback use an exact clean detached release and existing production
preflight. Web, completion, writer and GPU services are outside this deployment.

The initial production timer triggered at 08:52:00 KST and admitted four eligible
new holdings. It stopped before a title state changed because the service lacked
the existing shared title-lock environment. The service now points to the same
host lock folder as completion/web, and the existing read-only root validator
runs before seeding and during production preflight. The stopped cycle made no
model or NAS subtitle call; its error and queue history remain intact.

Corrected production release:
`dfa213762c94ec54671454f30c7f1c992bfcd835`, clean detached worktree at
`/opt/missav-dlp-web/discovery/stage11-normal-deployment/current`.
Read-only production preflight PASS including shared title-lock validation.
Rollback backup:
`/opt/missav-dlp-web/discovery/stage11-normal-deployment/backups/20261012-085324`.
The subtitle timer is enabled/active. Standard input is null and the queue owns
deployment authorization; no user approval or Codex model orchestration occurs.

The corrected cycle ran 08:53:43–08:57:50 KST. CAWB-039 progressed from PENDING
through RUNNING to FAILED_TERMINAL because external JA returned
VALIDATION_FAILURE/NOT_ATTEMPTED alignment. Its actual full baseline was saved;
temporary media cleanup passed. No Hermes, Korean SRT or NAS subtitle was produced
for this failed title. The runner exited 0 with a COMPLETE heartbeat and an
explicit failed_terminal=1 batch result; runner completion is distinct from
title success. Durable state/reason and immutable failure sidecar are preserved.
Counts at the audit: PUBLISHED163 (historical, unchanged), UNRESOLVED10
(historical, unchanged), FAILED_TERMINAL1, PENDING7. The timer will continue
other ordinary pending titles after 300 seconds without retrying this failed row.

Output storage and operational connection are verified by the actual canonical
SRTs, immutable completion readback, both existing Stage12 artifact preflights,
deployed clean release, shared title lock, native queue and heartbeat. Successful
new NAS publication was not exercised: the two successful comparison titles
already have ambiguous Korean inventories and must not be overwritten. The
existing no-overwrite publisher/Jellyfin path is reused, and all existing
publication/replacement smokes pass. This limitation is explicit in
`stage11-normal-mode-20261012/operation.json`.

Web login returned HTTP200, completion timer remained active, and the existing
library discovery writer remained running. No web/completion/writer/GPU service
was redeployed or restarted. Protected file audit was repeated after the live
cycle: all 2,213 pins and historical JA313/KO296/absorption17 still match.

Closure criteria 1–7 are recorded in `validation.json`. The normal-mode code,
reused absorption wiring, queue, deployment/rollback and this evidence are the
only new commit scope; original dirty work is preserved. No mandatory user task
remains. External-JA availability, unchanged alignment acceptance and Hermes
availability limit which titles can succeed; failed titles remain clearly failed.
