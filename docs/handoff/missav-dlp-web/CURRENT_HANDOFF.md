# Teddy Downloader / missav-dlp-web — CURRENT HANDOFF

## 2026-09-22 SNOS-120 Stage12 timeout forensic and recovery

The timeout cleanup fix is committed as
`2f26fe54e6c83029df5c7c9b06ea9f6cacdd76b4`. After that fix, the
operator completed explicit crash recovery for SNOS-120: `RUNNING -> PENDING`,
reason `CRASH_RECOVERY`, transition sequence `2 -> 3`.

Current authoritative rollout state after recovery:

- `PUBLISHED=128`, `PENDING=28`, `FAILED_RETRYABLE=16`, `UNRESOLVED=1`
- `ACTIVE_IDS=[]`
- `SNOS-120=PENDING`, transition sequence 3, reason `CRASH_RECOVERY`
- Bulk runner has not been restarted; no NAS/Jellyfin production write occurred.
- CT120 has no orphan process for the SNOS-120 session.

The counts below describe the earlier forensic snapshot before recovery.

At authorized HEAD `1208ce107a4ecc919fa90b254365a8e447c2fdda`, the
production bulk runner stopped on SNOS-120 (session
`28586729-7f58-5b69-99de-194a0e081567`, 564 cues, 9 parts). Read-only
rollout DB evidence: `PUBLISHED=128`, `PENDING=27`, `FAILED_RETRYABLE=16`,
`RUNNING=1` (SNOS-120), `UNRESOLVED=1`; SNOS-120 transition sequence 2,
reason `STAGE12_BATCH_START`. No runner process was present on CT108. CT120
read-only process and runtime-marker checks found no process or marker for the
session at investigation time; no orphan cleanup was performed.

Root cause: `_invoke_hermes_part()` observed an inactivity timeout after
600 seconds without output, stopped local SSH, then called remote timeout
cleanup. The remote script emitted `REMOTE_TIMEOUT_CLEANUP_RESULT=CMDLINE_MISMATCH`
and exited 26, preserving its fail-closed PID identity check. That exit made
`_cleanup_timed_out_remote_hermes()` raise exactly `StatefulLiveRunnerError(
"remote Hermes timeout cleanup failed")`, with no explicit cause or context.
It happened before `_invoke_hermes_part()` could construct its typed
`StatefulLiveRunnerTimeoutError`. Its broad diagnostic handler printed
`HERMES_INVOCATION_TIMEOUT_REASON=NONE` and `RESULT=FAIL` because that handler
does not pass the already-set timeout reason. Stage12's exact title-exception
boundary does not classify generic `StatefulLiveRunnerError`, so it wrapped
the error in `Stage12BatchSystemicError("unexpected Stage11 title execution
exception")`. The production log does not contain a Python traceback; this
exception chain is established from its unique marker sequence and the
authorized source path.

Generic fix: once timeout is observed, catch only `StatefulLiveRunnerError`
from remote cleanup and retain it as the explicit `__cause__` of the primary
`StatefulLiveRunnerTimeoutError`. Emit the original timeout reason and
`RESULT=TIMEOUT`. The remote cmdline/CWD/session/PGID checks and fail-closed
behavior remain unchanged. Unexpected programming or transport exceptions
remain systemic.

Validation: stateful live runner smoke, timeout smoke (including stalled fake
process, successful remote process-group cleanup, cleanup failure and exact
CMDLINE_MISMATCH exception), Stage12 batch smoke (timeout isolation and
programmer/systemic retention), Stage12 bulk runner smoke, Python compile,
and `git diff --check` all passed. No production Hermes retry, DB write,
`recover_running()`, NAS/Jellyfin write, bulk restart, or remote kill occurred.

Operator next action: review the recovered `PENDING` state and the committed
timeout fix before any separately authorized bulk restart. Do not recover
SNOS-120 again.

> Canonical handoff for the next chat/session.  Read this file first and continue from here rather than reconstructing Stage11/Stage12 from old chat history.
>
> Last refreshed for chat handoff: **2026-09-23 KST**

## 0. 2026-09-20 HMN-899 Stage12 systemic-stop forensic and fix

The root-cause fix is committed as
`e33dc36e83d03e863aafcebc1017cab089107a96`. After that forensic session,
the operator completed the explicit crash recovery for `HMN-899`:
`RUNNING -> PENDING`, reason `CRASH_RECOVERY`, transition sequence `2 -> 3`.
There are now no active rollout IDs. The bulk runner has not been restarted,
and no NAS or Jellyfin production write occurred during recovery.

Current authoritative rollout state after recovery:

- `PUBLISHED=65`, `PENDING=102`, `FAILED_RETRYABLE=5`, `UNRESOLVED=1`
- `ACTIVE_IDS=[]`
- `HMN-899=PENDING`, transition sequence 3, reason `CRASH_RECOVERY`
- bulk runner not restarted

Authoritative read-only state at investigation time:

- `PUBLISHED=65`, `PENDING=101`, `FAILED_RETRYABLE=5`, `RUNNING=1`,
  `UNRESOLVED=1`
- `HMN-899` rollout source: `HMN/HMN-899/HMN-899.mp4`, size
  `3847055679`, mtime_ns `1788055221873611116`
- exact NAS `lstat`, obtained through
  `teddy_discovery_stage12_rollout.build_nas_preflight_filesystem`, matched all
  three identities and confirmed a regular file

A bounded `/tmp` forensic reproduction copied the exact canonical source,
verified the copied snapshot, and requested only the first production-shaped
600-second audio chunk. Source copy succeeded in about 30 seconds. Audio decode
then raised exactly:

`teddy_discovery_asr_audio.ASRAudioValidationError: audio frame timestamp has an unsafe discontinuity`

The exception had no `__cause__` and no unsuppressed `__context__`; that single
exception is the complete chain. It occurred in `_validate_frame_timeline()`
while advancing `iter_audio_chunks()`, before the first chunk was yielded, so
the Remote ASR HTTP boundary was never called.

Root cause of the bulk-wide stop was a Stage12 typed-boundary omission.
`FullTitleASRTranscriber` deliberately preserves `ASRAudioError` from its audio
iterator, but `Stage12BatchRunner._is_title_exception()` did not recognize that
typed operational media failure. `_run_one()` consequently wrapped it as
`Stage12BatchSystemicError("unexpected Stage11 title execution exception")` and
stopped the immutable batch while leaving the already-transitioned title
`RUNNING`.

The minimal generic fix adds only the `ASRAudioError` hierarchy to the Stage12
title-exception tuple. It does not catch all `Exception` or all `ASRError`, does
not weaken audio validation, and has no DVD/title-specific condition. A new
Stage12 batch regression proves that the exact `ASRAudioValidationError` is
recorded as `FAILED_RETRYABLE` and the next selected title proceeds; existing
tests continue to prove unrelated `RuntimeError`, generic live-runner,
deployment, and explicit systemic failures stop the batch.

Validation passed:

- Python compile for the changed batch module and smoke
- Stage11 ASR source, audio, Remote ASR, and full-title transcriber smokes
- Stage11 live-adapters and controller smokes
- Stage12 batch and bulk-runner smokes
- `git diff --check`

Operator next action: restart the bulk runner under normal authorization. The
stale `HMN-899` state has already been explicitly recovered; do not run crash
recovery for it again.

## 1. Immediate Goal

The next session has three ordered goals:

1. **Resolve the current `EBWH-350` Stage12 failure generically and safely.**
2. **Finish Stage12 holdings subtitle rollout and formally close Stage12.**
3. **Start Stage13 — Downloader NAS Library File Manager** using the already-built Discovery inventory rather than broad NAS scans.

Do not start Stage13 implementation until Stage12 is formally reconciled/closed, except for read-only planning if needed.

---

## 2. Overall Project Status

- Stage0–10: **CLOSED / PASS**
- Stage11: **CLOSED / PASS**
- R6: **CLOSED / PASS**
- Stage12: **ACTIVE** — holdings Korean-subtitle rollout / operations / hardening
- Stage13: **NOT STARTED** — scope frozen in this handoff for later implementation

Stage11 must **not** be redesigned or reopened just to solve rollout failures. Stage12 owns durable rollout state, publication, failure isolation, NAS placement, and Jellyfin recognition.

The Stage11 controller remains publication-free (`publication_performed=false`). Stage12 publishes only after a valid Stage11 CLEAN result.

---

## 3. Repository / Canonical Paths

Repository:

- GitHub: `ssikgun/missav-dlp-web`
- working tree on CT108: `/opt/missav-pwa-subtitle-stage11`
- branch: `teddy-subtitle-stage11`
- Git common dir: `/opt/missav-pwa-src/.git`
- canonical handoff: `docs/handoff/missav-dlp-web/CURRENT_HANDOFF.md`

Source-code HEAD immediately before this handoff-only refresh:

- `425276ea0b3252435fb19634c6ab864ba7a544a4`
- commit message: `Add activity-aware Hermes timeout`

Because this canonical handoff may be committed through GitHub directly, the CT108 worktree may be one handoff-only commit behind `origin/teddy-subtitle-stage11`. At the beginning of the next session, **fetch and fast-forward only** before making source edits; do not reset or overwrite local work blindly.

Suggested synchronization on **root@downloader (CT108)**:

```bash
cd /opt/missav-pwa-subtitle-stage11
git status --short
git fetch origin teddy-subtitle-stage11
git merge --ff-only FETCH_HEAD
git status --short
```

If the worktree is not clean or fast-forward fails, stop and inspect before doing anything else.

---

## 4. Infrastructure / Server Map

These are the servers directly involved in Stage11–13.

| Role | Host / IP | Important details |
|---|---|---|
| Downloader / Stage12 controller | **CT108 `downloader` — `192.168.1.155`** | repo/worktree `/opt/missav-pwa-subtitle-stage11`; production `/opt/missav-dlp-web`; Python `/opt/stage11-stt-venv/bin/python` |
| GPU ASR | **VM122 `local-llm` — `192.168.1.134`** | RTX 3060 12GB; ASR worker port `8091`; `/v1/asr/transcribe`, `/v1/asr/transcribe-targeted`; large-v3 CUDA/float16 |
| Hermes semantic worker | **CT120 `hermes-lxc-slack` — `192.168.1.230`** | Hermes binary `/home/teddy/.local/bin/hermes`; subtitle profile `/home/teddy/.hermes/profiles/subtitle-translator` |
| Synology NAS | **`192.168.1.201`** | managed media root `/volume1/video/video2/JAV`; user `ssikgun`; publication must be exact-path/bounded |
| Jellyfin | **`192.168.1.205:8096`** | external Korean SRT recognition; use normal item/library refresh only; direct Jellyfin DB writes forbidden |

CT108 → CT120 production SSH identity:

- user: `teddy`
- key: `/root/.ssh/id_ed25519_stage11_hermes`
- known_hosts: `/root/.ssh/known_hosts_stage11_hermes`

CT108 → NAS publication identity:

- key: `/opt/missav-dlp-web/teddy-nas-transfer/id_ed25519`
- known_hosts: `/opt/missav-dlp-web/teddy-nas-transfer/known_hosts`
- private key mode `0600`
- known_hosts mode `0644` is accepted and working; do not chmod it merely for a temporary check.

Stage12 data:

- Discovery DB: `/opt/missav-dlp-web/discovery/teddy-discovery.sqlite3`
- Stage12 rollout DB: `/opt/missav-dlp-web/discovery/stage12-rollout-state.sqlite3`
- rollout writer lock: `/opt/missav-dlp-web/discovery/stage12-rollout-state.sqlite3.lock`
- SubtitleCat-only Gluetun proxy: `http://127.0.0.1:58888`

---

## 5. Frozen Architecture / Safety Policy

Generic title flow:

`canonical holding → baseline ASR → external JA attempt → safe HYBRID else ASR_ONLY → source-quality → targeted evidence when required → stateful semantic translation/review → deterministic CLEAN → mechanical report → Stage12 publication`

Hard rules:

- no title-, DVD-ID-, cue-, or literal-text-specific production branching
- specific titles/cues may be used only as canary/audit/operator-selected evidence
- no broad recursive NAS scan
- no overwrite of existing canonical Korean subtitle
- no direct Jellyfin DB modification
- no automatic video modification
- fail closed on stale/corrupt/source-mismatched artifacts
- baseline/targeted ASR may be reused only through existing provenance checks
- uncertain subtitle content should generally be conservatively retained; the user accepts practical comprehension rather than commercial-grade translation
- do not weaken validators merely to force a title through

User-approved quality bar:

- understandable Korean subtitles are the goal
- awkward wording / some Whisper hallucination may remain
- suspected phrases such as `시청해 주셔서 감사합니다` are not automatically deleted without evidence
- uncertain KEEP is preferred to false deletion

---

## 6. Current Stage12 Rollout State

Authoritative inventory originally contained **173 holdings**:

- 172 eligible for canonical KO subtitle
- 1 unresolved: `JUR-750`

Current durable rollout counts after the latest `EBWH-350` canary failure remain:

- **PUBLISHED = 21**
- **FAILED_RETRYABLE = 3**
- **PENDING = 148**
- **UNRESOLVED = 1**
- **RUNNING = 0**
- **GENERATED = 0**

The remaining three `FAILED_RETRYABLE` titles are:

1. `DASS-884`
2. `DVDES-795`
3. `EBWH-350`

`JUR-750` is the separate `UNRESOLVED` title because a noncanonical sidecar already exists:

`JUR-750.R6B2-Clean.ko.srt`

Do not rename/delete/overwrite that automatically. Resolve it explicitly near Stage12 closure.

---

## 7. Activity-aware Hermes Timeout — Frozen Candidate

Commit:

- `425276ea0b3252435fb19634c6ab864ba7a544a4`

Current production candidate behavior:

- semantic policy default: `stage11-stateful-cue64-v1`
- model-input normalization: `stage11-model-input=repeat-v2`
- model validation attempts: `2`
- inactivity timeout: **600 seconds**
- **any stdout or stderr bytes reset the inactivity deadline**
- child output is forwarded/flushed live to the caller log
- absolute timeout: **3600 seconds**
- absolute timeout never resets
- timeout reason is explicit: `INACTIVITY_TIMEOUT` or `ABSOLUTE_TIMEOUT`
- timeout diagnostics include configured limits, invocation elapsed time, and seconds since last output activity
- promoted semantic parts are preserved on timeout
- no adaptive 16/64/128 fallback

Direct CT108 validation before the live canary passed:

- `git diff --check`
- `py_compile`
- activity-aware timeout smoke: 19 PASS / 0 FAIL
- retry smoke: 27 PASS / 0 FAIL
- live-runner contract smoke: 16 PASS / 0 FAIL
- stateful policy smoke: 17 PASS / 0 FAIL
- Stage12 batch smoke
- Stage11 live-adapters smoke

Important limitation:

The latest `EBWH-350` live canary confirmed the new timeout wiring in the real path, but it **did not directly exercise an active invocation continuing beyond 600 seconds**. All completed calls in that canary were below 600 seconds. Therefore the implementation is strongly smoke-tested and live-wired, but the exact `>600s while still producing output` behavior is not yet directly demonstrated by a production title.

`DASS-884` is a likely natural live case for that later because its previous failure was at part 28 after a hard 600-second wall-clock timeout.

---

## 8. EBWH-350 — CURRENT BLOCKER

### 8.1 Latest canary identity

Temporary runner:

- `/tmp/stage12-timeout-canary-ebwh350.py`

Canary namespace:

- `stage12-ebwh350-timeout-canary-425276ea-v1`

Fresh semantic session:

- `276cbd34-db1e-58e6-b5b6-858815b99e37`

Title shape:

- `CUE_COUNT=925`
- `PART_COUNT=15`

Previous timed-out session that was intentionally not reused:

- `a79234c6-e9d3-5461-ba4d-19814931e39f`

### 8.2 Preflight incident and solution — SQLite `-shm` false positive

Initial direct preflight failed even though it was read-only:

- `production SQLite fingerprint changed during preflight read`
- `TITLE_STATE=UNKNOWN`
- NAS source/KO verification then failed downstream because the DB read was rejected

Root cause was proven directly:

- quiet two-second period: no DB metadata change
- every `_read_rollout_and_discovery()` call changed **only** `teddy-discovery.sqlite3-shm` `mtime_ns`
- the main DB, WAL, rollout DB did not change
- no SQL mutation was requested

SQLite read-only WAL access can update the transient SHM metadata. Therefore using SHM `mtime_ns` as durable mutation evidence caused a false positive.

Temporary canary fix:

- main DB + WAL continue to use strict fingerprinting
- SHM is checked only for stable structure/safety (`dev`, `ino`, `size`, mode/type); SHM `mtime_ns` is excluded
- no `immutable=1` shortcut was introduced

After that fix, direct preflight passed **18/18**:

- `HEAD_MATCH=YES`
- `WORKTREE_CLEAN=YES`
- `TITLE_STATE=FAILED_RETRYABLE`
- source snapshot PASS
- baseline ASR provenance PASS
- targeted provenance PASS
- CT120 / VM122 / NAS / Jellyfin connectivity PASS
- exact NAS KO absent
- remote task root absent and unprovisioned
- timeout wiring PASS
- production writes 0
- `READY_FOR_EBWH350_TIMEOUT_CANARY=YES`

This SHM handling was applied to the **temporary canary runner**. Before broad use, decide whether the same generic read-only fingerprint rule belongs in reusable tooling; do not blindly copy temp-runner code into production without smoke coverage.

### 8.3 Latest live canary result

Parts **1–9 were validated and promoted**.

At part 10:

- first Hermes invocation: **PASS**, ~`159.360673s`, timeout reason `NONE`
- validator: `INVALID_KO`
- retry occurred
- second Hermes invocation: **PASS**, ~`135.148759s`, timeout reason `NONE`
- validator: `INVALID_KO` again
- final semantic result: `SEMANTIC_OUTPUT_VALIDATION_RETRY_EXHAUSTED=10`

The rollout DB correctly transitioned `EBWH-350` back to:

- `FAILED_RETRYABLE`
- reason: `STAGE12_SEMANTIC_OUTPUT_VALIDATION_RETRY_EXHAUSTED`

No NAS publication or Jellyfin mutation occurred.

### 8.4 Critical cue evidence — `asr-000624`

Read-only forensic proved that cue `asr-000624` already contains a long repetition in the **authoritative source input**:

- authoritative `stt_ja` length: `223`
- content is essentially repeated `え?` tokens many times

The same long repeated source is present in `stage11-semantic-input.json`.

Hermes part-10 output translated that into a very long repeated Korean sequence such as repeated `어?`.

Follow-up forensic identified the exact edge case. The authoritative source contains 74 spaced `え?` tokens with a leading delimiter. The source-aware KO validator itself is behaving correctly: it rejects genuine model amplification and must remain unchanged. The gap was in `repeat-v1` model-input normalization, which handled compact contiguous repetition but did not recognize identical short units separated by bounded horizontal whitespace. Hermes therefore received the pathological 74-token model input and amplified it further.

Do **not** solve this by title hardcode or by disabling the repetition validator.

### 8.5 Separate temporary runner reporting bug

After the Stage12 logic had already transitioned the title back to `FAILED_RETRYABLE`, the temporary canary runner crashed while printing the title result:

`NameError: name '_session_reader' is not defined`

Location in the temp runner:

`_emit_title_result()` → `actual_session = _session_reader(result.dvd_id)`

This happened **after** the true semantic failure had already been recorded. The rollout DB was not left `RUNNING`.

Treat this as a **temporary canary/reporting harness bug unless production code proves otherwise**. Fix it before reusing this temp runner so later failures are reported cleanly.

### 8.6 EBWH-350 forensic resolved — `repeat-v2` ready for bounded live retry

The read-only forensic and generic correction are complete.

Confirmed root cause:

1. `asr-000624` authoritative raw `stt_ja` is length `223` and contains 74 repeated short tokens separated by spaces, with a leading delimiter;
2. `repeat-v1` did not normalize that shape because its model-input repetition scanner required contiguous repeated units;
3. the source-aware validator strips whitespace for source evidence but still evaluates the full source string, so the leading delimiter prevents whole-string periodic evidence;
4. Hermes received the pathological unbounded model input and produced an even larger Korean repetition;
5. the validator therefore correctly rejected the amplified KO. **The validator was not weakened.**

Generic fix implemented locally:

- model-input identity advanced to `stage11-model-input=repeat-v2`;
- identical short units separated by one identical, bounded horizontal-whitespace separator can now be reduced to two representative units;
- line boundaries are never crossed;
- ordinary Japanese and ambiguous Unicode remain unchanged/fail-closed;
- authoritative raw source objects remain byte-for-byte separate from the model-input projection;
- stale or duplicate `stage11-model-input=*` generation identities now fail closed instead of accumulating multiple identities;
- no title, cue, or literal production hardcode was added.

Focused verification completed:

- Python compile: PASS;
- model-input normalization smoke: `28 PASS / 0 FAIL`;
- stateful translator smoke: PASS;
- stateful parts smoke: `45 PASS / 0 FAIL`;
- stateful policy smoke: `17 PASS / 0 FAIL`;
- live runner smoke: `16 PASS / 0 FAIL`;
- retry smoke: PASS;
- activity-aware timeout smoke: PASS;
- `git diff --check`: PASS.

Source-shaped forensic verification also passed:

- raw length remains `223`;
- raw token count remains `74`;
- model-input token count becomes `2`;
- projected model text is `- え? え?`;
- generation key contains `stage11-model-input=repeat-v2`;
- bound session identity differs from the old unbound session.

No Hermes live call, NAS publication, Jellyfin mutation, or production DB write was performed during this fix.

**Next action:** fix the separate temporary EBWH canary `_session_reader` reporting bug, ensure the retry uses a fresh `repeat-v2` semantic session rather than the old `repeat-v1` session, then run one bounded `EBWH-350` recovery canary with the existing fixed64 / inactivity-600 / absolute-3600 / attempts-2 safety contract.

---

## 9. Other Remaining Stage12 Failures

### DASS-884

Current known history:

- 1868 cues / 30 parts
- prior fixed64 recovery promoted parts 1–27
- part 28 hit the old hard wall-clock `600s` timeout
- remains `FAILED_RETRYABLE`
- no NAS/Jellyfin operation was performed for the failed attempt

After `EBWH-350` is resolved, use `DASS-884` as a bounded recovery candidate and observe whether the new activity-aware timeout naturally allows a still-active invocation to continue beyond 600 seconds. Do not claim success unless the live evidence actually crosses 600 seconds while output activity continues.

### DVDES-795

Prior failure was **not a timeout**:

- 1594 cues / 25 parts
- parts 1–4 promoted
- part 5 Hermes returned PASS and valid-looking output, but the remote pending artifact was missing
- generic `StatefulLiveRunnerError` was accidentally treated as systemic

Generic fix already frozen before the timeout work:

- specific `StatefulLiveRunnerPendingArtifactError`
- remote missing pending mapped explicitly
- only that specific missing-pending exception is title-level retryable
- other remote read/safety errors remain systemic
- promoted parts remain preserved

Commit containing that fix before the timeout commit:

- `0e9102bdc599e33e78c1534171157e250263b191`

It still needs one live bounded retry to prove the fix in production.

---

## 10. Important Past Incidents / Known Solutions

### Codex could edit files but could not Git commit

Symptom:

`git add` failed creating:

`/opt/missav-pwa-src/.git/worktrees/missav-pwa-subtitle-stage11/index.lock`

with `Read-only file system`.

Meaning:

- Codex sandbox could modify authorized worktree files but could not write the shared Git metadata.
- This was **not** evidence that CT108 Git itself was broken.

Solution:

- perform commit/push directly from **root@downloader (CT108)** after validating exact modified-file set and `git diff --check`.
- direct commit/push succeeded for the timeout work.

### Old Hermes timeout behavior

Old implementation used wall-clock `subprocess.run(..., timeout=600)`.

Observed historical failures:

- `DASS-884` part 28: ~600.000880 seconds
- `EBWH-350` old part 10: ~600.001017 seconds

Reasoning text existed before timeout, proving output had occurred, but old logs did not timestamp every chunk; they could not prove activity continued right up to second 600.

Solution:

- activity-aware `Popen`/selector runner now resets inactivity timer on stdout/stderr bytes and has independent absolute cap.

### DVDES-795 missing pending artifact

Root cause and solution are described above. Never broaden all `StatefulLiveRunnerError` to title-local; cleanup/safety/systemic errors must remain systemic.

### Source-aware repetition / model amplification history

The pipeline previously saw genuine model-amplified repetition as well as source-grounded repetition false positives. Generic source-aware handling remains in place. The original `repeat-v1` model-input normalization has now been superseded by separator-aware `repeat-v2`, while the validator remains fail-closed against genuine model amplification.

Do not regress to “long repeated text = delete/reject” without considering source evidence.

### CT108 memory incident during early CP6

An earlier CT108 SSH/unresponsiveness incident was memory/swap + I/O reclaim pressure, not VM122 ASR CPU.

Current CT108 allocation accepted during the project:

- memory: 10 GB
- swap: 1 GB

Browser/Selkies/Docker mixed workload contributed. `/dev/shm` was not the root cause.

---

## 11. Stage12 — Exact Remaining Work Order

Do these in order, one bounded checkpoint at a time.

### S12-1 — Resolve EBWH-350 generic `INVALID_KO`

- read-only validator/normalization forensic
- identify exact generic root cause
- implement generic source-aware fix
- smoke/regression tests
- fix temp canary `_session_reader` reporting defect
- run one bounded EBWH-350 recovery canary
- require full Stage11 PASS before publication
- verify exact NAS canonical KO and Jellyfin recognition

### S12-2 — Recover DVDES-795

- preflight current source/NAS/state
- exercise already-frozen missing-pending-artifact fix
- isolate failure if another issue occurs
- publish/Jellyfin only after full PASS

### S12-3 — Recover DASS-884

- preflight current source/NAS/state
- bounded fixed64/repeat-v2 recovery
- observe activity-aware timeout behavior
- preserve promoted parts according to current contract
- publish/Jellyfin only after full PASS

### S12-4 — Reconcile the three failure titles

Expected target before broad rollout:

- no `RUNNING` or `GENERATED` orphan
- each of the three is either `PUBLISHED` or an explicit still-visible failure with correct provenance
- do not silently hide failures

### S12-5 — Roll remaining `PENDING=148`

Use bounded serial rollout with durable resume/failure isolation.

Requirements:

- fixed64 default
- repeat-v2 normalization
- activity-aware Hermes timeout
- existing validators unchanged except evidence-backed generic fixes made above
- exact NAS KO check before title execution/publication
- existing KO protected
- baseline/targeted artifacts reused only through provenance checks
- each failed title isolated; batch continues according to the approved batch contract
- live log available while long jobs execute

Do not launch all 148 blindly before the three known failure classes have been reconciled.

### S12-6 — Resolve `JUR-750`

Explicit operator-safe decision for existing noncanonical:

`JUR-750.R6B2-Clean.ko.srt`

No automatic rename/delete/overwrite.

### S12-7 — Final Stage12 reconciliation and closure

Closure checklist:

- all 173 holdings accounted for
- `PENDING=0`
- `RUNNING=0`
- `GENERATED=0`
- every eligible title has an explicit terminal/accounted result
- valid published KO subtitles exist at exact canonical NAS paths
- existing KO files preserved
- Jellyfin recognizes published Korean external subtitles
- failures, if any are intentionally accepted, remain explicit and documented rather than hidden
- JUR-750 resolved explicitly
- canonical handoff updated
- commit/push clean
- Stage12 marker changed to **CLOSED / PASS** only when the closure criteria are actually met

---

## 12. Stage13 — Downloader NAS Library File Manager

Stage13 starts **after Stage12 formal closure**.

### Goal

Add a user-facing **File Management** section/tab to Downloader for the managed JAV library under:

`/volume1/video/video2/JAV`

It should behave like an operational library manager built on the existing Discovery inventory, not like a generic filesystem browser.

### Required capabilities

#### Inventory / browsing

- persistent inventory backed by existing Discovery data where possible
- no broad recursive NAS scan on every page load
- bounded reconcile/update mechanism
- expandable title/work rows similar to Discovery
- show useful metadata for each managed work
- screenshots/images may be shown/listed
- **video preview is not required**

#### Search

Search by at least:

- DVD-ID / product code
- title

Jellyfin search quality should also be improved so DVD-ID/product-code lookup is reliable rather than depending only on title text.

#### Korean subtitle status

KO subtitle state is a first-class field:

- canonical KO present / absent
- ideally valid / unresolved state when useful
- filter: KO present
- filter: KO absent

Reuse Stage12 canonical subtitle/path rules rather than inventing a conflicting second definition.

#### Sort

Support practical sorts including:

- download/addition date
- Korean subtitle state
- release date
- DVD-ID / product code
- title

#### Deletion

Deletion is destructive and must be implemented only after read-only inventory/browse behavior is proven.

Safety requirements:

- delete only one exact managed work/title at a time
- explicit user confirmation
- canonical root containment under `/volume1/video/video2/JAV`
- reject traversal
- reject symlink escape
- no broad wildcard/recursive delete outside the exact managed title directory
- fail closed on inventory/path identity mismatch
- update durable inventory only after filesystem result is verified
- trigger normal Jellyfin refresh/reconcile after deletion
- never modify Jellyfin DB directly

Before choosing delete semantics, inspect **Synology recycle-bin behavior** for this share and decide whether deletion should intentionally use or bypass recycle behavior. Do not assume.

### Suggested Stage13 implementation order

1. **Stage13 CP1 — read-only inventory contract**
   - map Discovery holding → exact NAS managed work path
   - verify metadata fields / KO state / screenshot enumeration contract
   - no filesystem mutation

2. **Stage13 CP2 — File Management UI shell**
   - browse, expand, search, filter, sort
   - read-only only

3. **Stage13 CP3 — bounded inventory reconcile/cache**
   - durable/updateable without broad page-load scans

4. **Stage13 CP4 — deletion preflight / safety contract**
   - exact title path
   - containment/symlink checks
   - confirmation model
   - Synology recycle behavior verified
   - dry-run only

5. **Stage13 CP5 — one-title deletion canary**
   - only with explicit user authorization
   - verify filesystem result + Discovery state + Jellyfin refresh

6. **Stage13 CP6 — operational hardening / closure**

Stage13 must reuse Discovery rather than creating an unrelated second library index unless a separate cache is technically required. If a cache is introduced, Discovery remains the authoritative logical inventory and reconciliation must be explicit.

---

## 13. Major Recent Commits / Milestones

Useful recent commits in chronological order:

- `7ae8d5e...` — Stage11/R6 closure
- `16346e8...` — Stage12 scope
- `86336ad...` — CP1 inventory
- `9e75621...` — CP2 rollout state
- `06c8bfa...` — CP3 NAS publication
- `c0baa59...` — CP4 Jellyfin recognition
- `6a1c801...` — CP5 3-title rollout/reconciliation
- `ac39754...` — alignment-limit safe fallback
- `cecefa11...` — bounded semantic retry/per-title isolation
- `9e9fde3f...` — Hermes timeout isolation
- `9363646f...` — CP6 closure handoff
- `b65ae36f...` — source-aware repeated cue fix
- `35b85adf...` — fixed64 rollout candidate
- `2264f8f0...` — fixed64 promoted as stateful default
- `0e4d64b9...` — pathological repetition normalization before Hermes
- `23c2f17c...` — orphan-state recovery
- `4021898c...` — normalized EROFV-387 recovery
- `0e9102bdc599e33e78c1534171157e250263b191` — missing pending-artifact typed recovery
- `425276ea0b3252435fb19634c6ab864ba7a544a4` — activity-aware Hermes timeout

Do not assume abbreviated SHAs are unique without `git rev-parse` when performing source changes.

---

## 14. Working / Reporting Rules for the Next Chat

The user prefers short, practical reporting.

For pasted terminal/Codex results:

- first visible token must be exactly one of: `PASS`, `FAIL`, `INCOMPLETE`
- explain the key meaning in simple Korean
- distinguish confirmed facts from inference / needs-checking
- give **exactly one next checkpoint**
- do not dump unnecessary theory/log repetition

Command discipline:

- always state execution location near command blocks (`root@downloader (CT108)`, `teddy@local-llm (VM122)`, `teddy@hermes-lxc-slack (CT120)`, etc.)
- one checkpoint at a time
- no blind retry
- for real long-running live commands, provide a **real-time log viewing command** (`tee`, `tail -f`, or a filtered watcher)
- do not use shell-killing patterns such as `exit`, naked `false`, `set -e`, `set -eu`, `set -euo pipefail`, `|| exit 1`, shell-replacing `exec`, or `kill $$`
- avoid broad NAS `find`, `os.walk`, `rglob`, or `du`; use exact/bounded paths

Implementation discipline:

- prefer Codex for bounded implementation/smoke/forensic work
- do not make Codex wait on long Hermes production runs
- long live Hermes jobs run directly from CT108 in background with observable logs
- important source changes require canonical handoff update and commit/push
- do not modify unrelated projects/files

---

## 15. First Checkpoint in the New Chat

The `EBWH-350` validator forensic and generic `repeat-v2` implementation are complete and smoke/regression tested.

Do **not** redo the validator investigation and do **not** weaken the validator.

The immediate next checkpoint is:

1. inspect/fix the temporary EBWH canary `_session_reader` reporting bug only;
2. verify that the bounded retry will create/use a fresh `repeat-v2` semantic session and will not reuse the old `repeat-v1` semantic session;
3. run one observable bounded `EBWH-350` recovery canary;
4. publish to NAS/Jellyfin only if the complete Stage11 result reaches valid CLEAN through the normal Stage12 publication path.

If the live recovery fails, keep the failure title-local as `FAILED_RETRYABLE` and inspect the new evidence before changing policy.

After `EBWH-350` is resolved, continue the existing Stage12 remaining-work order toward formal closure, then start Stage13.

## 2026-09-17 — EBWH-350 repeat-v2 live forensic + semantic repetition policy

### Status

- Stage12 remains **ACTIVE**.
- EBWH-350 repeat-v2 bounded live canary did **not publish** and remains `FAILED_RETRYABLE`.
- Parts 1–9 validated/promoted successfully.
- Part 10 ended at the controller with `INACTIVITY_TIMEOUT`.
- NAS publication: **NOT_RUN**
- Jellyfin refresh: **NOT_RUN**

### EBWH-350 repeat-v2 forensic result

The repeat-v2 model-input normalization itself is confirmed working correctly.

For the problematic source cue:

- authoritative/raw `stt_ja`: 74 spaced repetitions
- local semantic/model input: 2 representative repetitions
- remote CT120 semantic input: 2 representative repetitions
- Hermes part-10 output: 87 Korean repetitions

Therefore the remaining repetition failure is **not** a repeat-v2 projection/wiring failure.
Hermes semantically re-expanded a correctly bounded model input.

The existing output validator correctly rejected this kind of runaway result and was not weakened.

### Part-10 timeout / remote lifecycle finding

The part-10 remote pending artifact existed and was structurally complete before the controller timed out.

Observed:

- remote `semantic-part-0010.pending.json` mtime was about 42 seconds after part start
- JSON parsed successfully
- cue coverage: 64 / 64 unique, correct first/last cue IDs
- controller later reached the 600-second inactivity timeout
- CT120 still had the exact subtitle-translator shell/Hermes process alive after the CT108 controller had already returned

This proves a separate remote lifecycle bug:

- controller timeout can leave the remote Hermes task/process running
- manual forensic cleanup terminated the exact orphan task processes
- generic Hermes dashboard/gateway and unrelated Codex processes were not targeted

This orphan cleanup behavior is **not yet fixed in production source**.

### Generic semantic repetition policy added

A shared stateful semantic repetition instruction is now used by both:

1. the initial whole-title `STATEFUL_TRANSLATOR_QUERY`
2. every resumed deterministic part query built by the stateful controller

Policy is generic and title-independent:

- excessive non-semantic repetition such as fillers/interjections/non-lexical vocalizations should be compressed to a short natural representative expression
- meaningful repetition, emphasis, stuttering, chanting, rhythm, or other scene-relevant repetition should be preserved
- translated output must not increase repeated units beyond the current authorized model-input evidence
- a longer repetition must not be reconstructed from earlier session history or historical artifacts
- uncertain repetition is retained conservatively rather than deleted

No DVD ID, work-specific phrase, cue ID, or title-specific literal is embedded in production policy.

### Validation

- Python compile: **PASS**
- stateful translator smoke: **PASS**
- stateful controller smoke: **29 PASS / 0 FAIL**
- stateful live runner smoke: **16 PASS / 0 FAIL**
- `git diff --check`: **PASS**

### Next work

Next highest-priority checkpoint:

**Fix the generic CT120 remote-process lifecycle so a controller timeout terminates/reaps only the exact remote subtitle-translator task and cannot leave an orphan Hermes invocation.**

After that fix and regression smoke, run a fresh bounded EBWH-350 canary session using:

- repeat-v2 model input
- the new generic semantic repetition policy
- the fixed remote timeout cleanup path

Do not weaken semantic validators to force publication.

## 2026-09-17 — Remote Hermes timeout lifecycle cleanup

### Status

The CT120 orphan-Hermes timeout bug found during the EBWH-350 repeat-v2 canary is now fixed in production source.

Root cause:

- CT108 inactivity/absolute timeout stopped only the local SSH `Popen`
- the already-running CT120 `bash` / Hermes process could survive after SSH termination
- this was live-proven during the EBWH-350 part-10 timeout

### Fix

The stateful live runner now uses task-scoped runtime ownership markers:

- `.stage11-hermes-runtime.pid`
- `.stage11-hermes-runtime.meta`

Remote Hermes execution is started in its own process group with `setsid`.

On controller timeout, a second bounded SSH cleanup verifies all of the following before terminating anything:

- expected CT120 hostname
- exact remote task directory exists
- PID and metadata files exist and are valid
- metadata session ID exactly matches the current Stage11 session
- `/proc/<pid>/cwd` exactly matches the current remote task directory
- `/proc/<pid>/cmdline` identifies the subtitle-translator Hermes invocation
- exact `--resume <session_id>` is present
- process-group ID equals the recorded leader PID

Only after these checks does cleanup send TERM to the exact process group.
KILL is used only as a bounded fallback if that exact process remains alive.

No broad `pkill`, `killall`, or generic Hermes process scan is used.

Runtime marker files are removed after successful cleanup.
Existing semantic pending artifacts are not deleted by timeout cleanup.

### Validation

Synthetic end-to-end timeout lifecycle smoke: **PASS**

Confirmed:

- target timeout process group was terminated
- target process was reaped
- runtime PID/meta markers were removed
- unrelated concurrent Hermes process remained alive
- existing inactivity timeout classification still passes
- existing absolute timeout classification still passes
- activity-aware timeout behavior remains unchanged
- remote pending recovery contract remains unchanged
- `git diff --check`: **PASS**

### Next work

Run a fresh bounded EBWH-350 canary session using:

- repeat-v2 model-input normalization
- generic semantic repetition guard
- exact remote timeout lifecycle cleanup

Expected objective:

- verify the pathological source cue no longer expands in Korean output
- verify no CT120 orphan process remains if a timeout occurs
- publish nothing unless the existing semantic validators accept the result

## 2026-09-17 — EBWH-350 repeat-v2 production canary PASS

### Final result

EBWH-350 Stage12 recovery canary completed successfully.

Production result:

- Stage11 semantic translation: PASS
- total cues: 925
- total parts: 15
- all 15 parts validated and promoted
- NAS publication: PASS
- Jellyfin recognition: PASS
- final rollout state: `PUBLISHED`
- destination: `EBWH/EBWH-350/EBWH-350.ko.srt`

Final rollout counts:

- `PUBLISHED=22`
- `FAILED_RETRYABLE=2`
- `PENDING=148`
- `UNRESOLVED=1`

### Repetition regression proof

The previous failure occurred in part 10 around the pathological repeated cue.

With repeat-v2 plus the generic semantic repetition guard:

- the semantic input remained bounded
- Hermes did not regenerate the previous excessive repetition
- cue `asr-000624` produced Korean `어? 어?`
- part 10 passed current Stage11 validators
- validators were not weakened

This live run confirms the generic repetition policy works on the original failing production case.

### Timeout/orphan lifecycle proof

The live runner exited normally after the canary.

Post-run verification:

- local canary runner: exited
- `.stage11-hermes-runtime.pid`: absent
- `.stage11-hermes-runtime.meta`: absent

No stale CT120 runtime ownership marker remained.

The earlier timeout cleanup implementation had already passed synthetic exact-process-group cleanup validation.
This successful production run additionally confirms the normal-completion lifecycle leaves no runtime marker residue.

### Frozen EBWH-350 conclusion

EBWH-350 is closed as a successful Stage12 recovery case.

The validated production combination is:

- `stage11-model-input=repeat-v2`
- `stage11-stateful-cue64-v1`
- generic semantic repetition guard
- inactivity timeout: 600 seconds
- absolute timeout: 3600 seconds
- exact task/session-scoped remote Hermes lifecycle ownership
- existing Stage11 validators unchanged

### Remaining Stage12 failures

Two `FAILED_RETRYABLE` titles remain:

- DVDES-795
- DASS-884

EBWH-350 must not be retried again unless a new regression is discovered.

## 2026-09-17 — DVDES-795 production recovery PASS

### Final result

DVDES-795 Stage12 recovery completed successfully.

Production result:

- semantic session: fresh repeat-v2 session
- total cues: 1594
- total parts: 25
- all 25 parts validated and promoted
- Stage11 result: PASS
- NAS publication: PASS
- Jellyfin recognition: PASS
- final rollout state: `PUBLISHED`
- destination: `DVDES/DVDES-795/DVDES-795.ko.srt`

Final rollout counts:

- `PUBLISHED=23`
- `FAILED_RETRYABLE=1`
- `PENDING=148`
- `UNRESOLVED=1`

### Missing-pending regression proof

DVDES-795 previously failed after Hermes returned PASS for part 5 because the remote pending artifact was missing and the generic error path was treated as systemic.

The frozen generic fix introduced:

- `StatefulLiveRunnerPendingArtifactError`
- only the exact missing-pending condition is title-level retryable
- unrelated remote read/safety/systemic failures remain systemic
- previously promoted parts remain preserved

The production recovery passed the original failure boundary:

- part 5 validated successfully
- `PROMOTED_PART=5/25`
- execution continued through all 25 parts
- no validator weakening was required

This is the production proof for the missing-pending recovery contract.

### Current production policy

The successful recovery used:

- `stage11-model-input=repeat-v2`
- `stage11-stateful-cue64-v1`
- inactivity timeout: 600 seconds
- absolute timeout: 3600 seconds
- current Stage11 validators unchanged
- fresh semantic session; previous failed session was not reused

### Runtime cleanup verification

Post-run verification:

- local canary runner: exited
- `.stage11-hermes-runtime.pid`: absent
- `.stage11-hermes-runtime.meta`: absent

No runtime ownership marker remained on CT120 after successful completion.

### Remaining Stage12 failure

Only one `FAILED_RETRYABLE` title remains:

- `DASS-884`

`DVDES-795` must not be retried again unless a new regression is discovered.

## 2026-09-17 — DASS-884 production recovery PASS

### Final result

DASS-884 Stage12 recovery completed successfully.

Production result:

- fresh repeat-v2 semantic session
- total cues: 1868
- total parts: 30
- all 30 parts validated and promoted
- Stage11 result: PASS
- NAS publication: PASS
- Jellyfin recognition: PASS
- final rollout state: `PUBLISHED`
- destination: `DASS/DASS-884/DASS-884.ko.srt`

Final rollout counts:

- `PUBLISHED=24`
- `PENDING=148`
- `UNRESOLVED=1`
- `FAILED_RETRYABLE=0`

### Previous timeout recovery

The previous DASS-884 recovery used repeat-v1 with the old fixed 600-second wall-clock timeout.

That run:

- promoted through part 27/30
- requested part 28/30
- terminated at approximately 600.000880 seconds
- ended as `FAILED_RETRYABLE`

The successful recovery used the current production contract:

- `stage11-model-input=repeat-v2`
- `stage11-stateful-cue64-v1`
- inactivity timeout: 600 seconds
- absolute timeout: 3600 seconds
- current Stage11 validators unchanged
- fresh semantic session; previous failed session was not reused

Part 28 passed successfully in the new recovery and execution continued through part 30.

Note: this successful run proves recovery from the former part-28 failure, but it does not independently prove a >600-second live invocation surviving via activity reset because the successful part 28 completed below 600 seconds.

### Runtime cleanup verification

Post-run verification:

- local canary runner: exited
- `.stage11-hermes-runtime.pid`: absent
- `.stage11-hermes-runtime.meta`: absent

No runtime ownership marker remained on CT120 after successful completion.

### Stage12 current state

There are now no `FAILED_RETRYABLE` titles.

Remaining work:

- process the remaining `PENDING=148` titles
- resolve the single `UNRESOLVED=1` title separately
- the unresolved title is JUR-750 with its noncanonical KO sidecar condition

DASS-884 must not be retried again unless a new regression is discovered.

## 2026-09-17 — Pending5 malformed external JA fallback incident

### Incident

The first current-policy five-title Stage12 PENDING canary selected:

- EROFV-390
- EYAN-228
- FBOS-015
- FC2-PPV-4451371
- FC2-PPV-4551303

EROFV-390 completed successfully:

- route: `ASR_ONLY`
- Stage11: PASS
- NAS publication: PASS
- Jellyfin recognition: PASS
- final rollout state: `PUBLISHED`

The batch then claimed EYAN-228 as `RUNNING`.

Its external Japanese subtitle contained an invalid control character during
lexical alignment. `normalize_japanese_for_matching()` correctly raised
`AlignmentValidationError`, but the live external-JA adapter mapped only
`AlignmentLimitError` into `ExternalSubtitleValidationError`.

That validation error therefore escaped the intended external-subtitle
fallback boundary and Stage12 conservatively promoted the unexpected
exception to `Stage12BatchSystemicError`, stopping the serial batch.

### Generic fix

Production code now maps generic `AlignmentValidationError` from external-JA
alignment to `ExternalSubtitleValidationError`.

This preserves the existing controller contract:

malformed external JA -> external validation failure -> `ASR_ONLY`

The existing specialized `AlignmentLimitError` message remains unchanged.

No DVD-ID, title, cue, literal subtitle text, or work-specific production
condition was added.

Source-fix commit before this handoff update:

- `26b09202a87096726bfb1dd796a641c55b61d0b9`

Validation:

- alignment fallback smoke: PASS
- Stage11 live adapters smoke: PASS
- Stage11 controller smoke: PASS
- Stage12 batch smoke: PASS
- `git diff --check`: PASS

### Crash recovery

After the failed batch process had exited and all exact CT120 Hermes runtime
PID/meta markers were confirmed absent, EYAN-228 was recovered through the
existing official `Stage12RolloutStateStore.recover_running()` path:

`RUNNING -> PENDING`

Reason:

- `CRASH_RECOVERY`

EROFV-390 must not be rerun.

Current rollout counts after recovery:

- `PUBLISHED=25`
- `PENDING=147`
- `RUNNING=0`
- `UNRESOLVED=1`
- `FAILED_RETRYABLE=0`

### Next action

Resume only the four unfinished members of the original canary:

1. EYAN-228
2. FBOS-015
3. FC2-PPV-4451371
4. FC2-PPV-4551303

Use a fresh batch/runtime namespace and the current production contract:
cue64, repeat-v2, 600-second inactivity timeout, 3600-second absolute timeout,
retry count 2, and exact-process Hermes orphan cleanup.

## 2026-09-18 — Pending4 canary closure and Jellyfin FullRefresh fallback

### Pending4 canary final result

The four-title continuation canary ran on the current Stage11/Stage12
production contract:

- semantic policy: `stage11-stateful-cue64-v1`
- model input: `stage11-model-input=repeat-v2`
- inactivity timeout: 600 seconds
- absolute timeout: 3600 seconds
- model retries: 2
- exact-process Hermes orphan cleanup retained

Selected titles:

1. EYAN-228
2. FBOS-015
3. FC2-PPV-4451371
4. FC2-PPV-4551303

Final title states:

- EYAN-228: `PUBLISHED`
- FBOS-015: `PUBLISHED`
- FC2-PPV-4451371: `PUBLISHED`
- FC2-PPV-4551303: `PUBLISHED`

EYAN-228 confirmed the malformed-external-JA fallback fix in production:
the unsafe external Japanese candidate was rejected and the title continued
through `ASR_ONLY` instead of aborting the batch.

The canary also confirmed title-level isolation. FC2-PPV-4451371 encountered
a Jellyfin recognition failure after successful Stage11 generation and NAS
publication, but the serial batch continued and FC2-PPV-4551303 completed
successfully.

### FC2-PPV-4451371 Jellyfin recovery

For FC2-PPV-4451371:

- Stage11 result: PASS
- NAS publication: PASS
- durable CLEAN SHA-256:
  `c2e76532d5ba84b335815b1a7ca88a3e9a4300f1f4203e75e9709c08d2669fdb`
- NAS destination SHA matched the durable CLEAN artifact exactly
- Jellyfin Default item refresh did not discover the new external subtitle
- item-specific `MetadataRefreshMode=FullRefresh` discovered the exact
  external Korean SUBRIP stream
- official `Stage12RolloutStateStore.reconcile_published()` was used
- no controller rerun
- no translation rerun
- no NAS rewrite
- final state: `PUBLISHED`
- reconciliation reason: `PUBLICATION_RECONCILED`

### Generic Jellyfin production hardening

`teddy_discovery_stage12_batch.py` now retains the existing bounded
item-specific Default refresh first.

If the exact external Korean subtitle is still not visible after that polling
window, the same exact Jellyfin item receives one item-specific FullRefresh,
followed by the same bounded PlaybackInfo polling.

This is generic behavior:

- no DVD-ID-specific branch
- no title-specific path rule
- no subtitle-text-specific logic
- no library-wide refresh
- existing exact item/path/language/codec checks remain unchanged

Validation completed before handoff update:

- Python compile: PASS
- `teddy_discovery_stage12_batch_smoke.py`: PASS
- `teddy_discovery_stage12_rollout_smoke.py`: PASS
- `git diff --check`: PASS

### Current Stage12 rollout state

- PUBLISHED: `29`
- PENDING: `143`
- FAILED_RETRYABLE: `0`
- FAILED_TERMINAL: `0`
- RUNNING: `0`
- GENERATED: `0`
- UNRESOLVED: `1`

The one UNRESOLVED title remains JUR-750 and stays isolated from normal
PENDING rollout work.

### Next action

Resume Stage12 from the remaining ordinary `PENDING` titles under the current
generic production contract. Do not rerun already `PUBLISHED` titles.
Do not automatically include JUR-750 in normal PENDING processing.

## 2026-09-18 — Subtitle status mini-panel

### Goal

Expose Stage12 subtitle rollout status in the Downloader Settings page before
starting the remaining bulk subtitle rollout.

The panel is intentionally read-only and temporary in the Settings page.
It can later be moved to the future file-management page without changing
the status API contract.

### Implemented

New read-only endpoint:

- `GET /api/subtitles/status`

New components:

- `teddy_subtitle_status.py`
- `teddy_subtitle_status_smoke.py`
- `teddy_subtitle_status_ui_smoke.py`
- `templates/teddy-subtitle-status.css`
- `templates/teddy-subtitle-status.js`

Settings UI now displays:

- overall runner state
- current DVD ID
- current stage / part progress when heartbeat provides it
- PUBLISHED
- PENDING
- FAILED_RETRYABLE
- FAILED_TERMINAL
- UNRESOLVED
- last activity

The panel does not expose start/stop/retry controls.

### State sources

The status API reads the existing Stage12 rollout SQLite database read-only.

Production container contract:

- `TEDDY_SUBTITLE_STATE_PATH=/stage12/stage12-rollout-state.sqlite3`
- `TEDDY_SUBTITLE_HEARTBEAT_PATH=/stage12-runtime/status.json`

Production mounts:

- rollout DB: exact file, read-only
- heartbeat directory: read-only

The Downloader container never writes Stage12 rollout state or heartbeat.

### Runner-state contract

A remaining PENDING count does not mean the runner is active.

The UI distinguishes:

- `running`: fresh runner heartbeat says RUNNING
- `idle`: no live runner and no active rollout title
- `stale`: durable RUNNING/GENERATED state exists without a fresh heartbeat
- `attention`: retryable/terminal failures exist
- `error`: fresh runner heartbeat reports ERROR

Heartbeat freshness threshold is currently 120 seconds.

The upcoming bulk Stage12 runner must write the heartbeat atomically to:

`/opt/missav-dlp-web/discovery/stage12-runtime/status.json`

### Validation

Completed before deployment:

- Python compile: PASS
- subtitle status backend smoke: PASS
- subtitle status UI smoke: PASS
- existing Discovery UI shell regression: PASS
- `git diff --check`: PASS
- production compose validation: PASS

Current read-only rollout snapshot at implementation time:

- PUBLISHED: 29
- PENDING: 143
- FAILED_RETRYABLE: 0
- FAILED_TERMINAL: 0
- UNRESOLVED: 1
- runner status: idle

### Deployment state

Production compose was prepared with read-only Stage12 mounts and backed up
before modification.

The running production image has not yet been replaced.

The Docker workflow automatically builds on `teddy-custom` pushes only.
For this `teddy-subtitle-stage11` branch, use `workflow_dispatch` to build
the immutable `teddy-<commit SHA>` image. Do not promote the mutable
`teddy-custom` tag from this branch.

### Next action

Build the current `teddy-subtitle-stage11` commit through the existing
GitHub Actions workflow, pin the resulting immutable image in production,
verify `/api/subtitles/status` and the Settings mini-panel, then start the
remaining 143-title Stage12 production rollout with heartbeat reporting.

## 2026-09-18 — Stage12 bulk runner prepared

### Current production UI

The Downloader Settings subtitle-status mini-panel is deployed and verified.

Production web image:

- revision: `24f6a6c62058ea0ad4d0ec204b9c9ecc285c9de8`
- digest: `sha256:fb1e9c6dc655c3cd7044e8a8c1711414589e2c1695503e866fe178c3396e6b79`

The Stage12 rollout DB and heartbeat directory are mounted read-only inside
the Downloader container.

Current visible rollout state before bulk execution:

- PUBLISHED: 29
- PENDING: 143
- FAILED_RETRYABLE: 0
- FAILED_TERMINAL: 0
- UNRESOLVED: 1
- active RUNNING/GENERATED: 0

Dark-mode styling of the temporary Settings card is intentionally deferred
until the card is moved into the future file-management page.

### Formal Stage12 bulk runner

Added:

- `teddy_discovery_stage12_bulk_runner.py`
- `teddy_discovery_stage12_bulk_runner_smoke.py`

The runner reuses the existing production contracts rather than introducing
a new subtitle pipeline:

- deterministic eligible PENDING selection
- exact selected NAS inventory revalidation
- frozen Stage11 controller
- cue64 semantic policy
- repeat-v2 model input
- 600-second Hermes inactivity timeout
- 3600-second absolute timeout
- two validation attempts
- exact-process Hermes cleanup
- malformed external-JA fallback to ASR_ONLY
- serial Stage12 title isolation
- atomic no-overwrite publication
- exact Jellyfin external-KO recognition
- bounded Default-to-FullRefresh Jellyfin fallback

FAILED_RETRYABLE, FAILED_TERMINAL, PUBLISHED and UNRESOLVED titles are not
implicitly selected as normal bulk work.

No title/DVD-specific production branch is present.

### Heartbeat

The bulk runner writes an atomic heartbeat to:

`/opt/missav-dlp-web/discovery/stage12-runtime/status.json`

Heartbeat interval:

- 30 seconds

The heartbeat carries:

- runner state
- current DVD ID
- high-level stage
- process PID
- authorized Git HEAD
- batch number / processed count when available

If the runner dies without finalization, the Downloader status panel will
eventually show a stale runner state instead of falsely claiming normal
activity.

### Crash policy

The bulk runner does not silently recover durable RUNNING or GENERATED
states. If either exists at startup, preflight fails closed.

`RUNNING` crash recovery remains the explicit existing
`Stage12RolloutStateStore.recover_running()` procedure after exact runtime
verification. GENERATED/publication ambiguity remains subject to the existing
reconciliation rules.

### Validation before live authorization

Offline validation required before commit:

- Python compile
- bulk-runner smoke
- Stage12 batch smoke
- Stage12 rollout smoke
- `git diff --check`

The next checkpoint is a read-only bulk preflight on the committed clean
worktree. Actual 143-title execution remains separately authorization-gated.

## 2026-09-18 — Stage12 production first4 PASS

Formal production Stage12 bulk execution was started with the repository
runner `teddy_discovery_stage12_bulk_runner.py`.

First production batch:

- FC2-PPV-4555371
- FC2-PPV-4575470
- FC2-PPV-4592689
- FC2-PPV-4640215

Result:

- processed: 4
- published: 4
- FAILED_RETRYABLE: 0
- FAILED_TERMINAL: 0
- systemic failure: none

Durable rollout state after completion:

- PUBLISHED: 33
- PENDING: 139
- UNRESOLVED: 1
- RUNNING/GENERATED: 0

The production runner heartbeat operated correctly and the Downloader
Settings mini-panel showed the current DVD ID and active processing state.

Deferred mini-panel improvements for the future File Management tab:

1. match the Downloader dark theme
2. replace internal stage names such as `STAGE11` with plain Korean labels
   such as `자막 생성·번역 중`
3. expose real stateful part progress from the execution path and show
   `current part / total parts` plus optional percentage

Do not derive part progress heuristically. It must come from the actual
stateful/Hermes part execution state.

Next operation:

- launch the same formal production runner for all remaining ordinary
  PENDING titles
- no new canary implementation
- no title-specific production logic

## 2026-09-19 — Stage12 malformed external JA incident

The long-running Stage12 production bulk stopped during batch 9.

Durable state at the stop:

- PUBLISHED: 63
- PENDING: 104
- FAILED_RETRYABLE: 4
- RUNNING: 1
- UNRESOLVED: 1
- stuck RUNNING title: `HAWA-345`

The bulk process was no longer running and heartbeat finalized as ERROR.

Root cause was confirmed by an exact route-only replay using the already
persisted HAWA-345 baseline artifact:

- external Japanese subtitle SRT contained an invalid non-positive cue index
- subtitle parser raised `SubtitleParseError`
- immutable Hybrid construction wrapped this as
  `HybridEvidenceValidationError`
- the live external-JA adapter did not map that evidence-validation failure
  into its normal external-subtitle validation boundary
- Stage12 therefore treated it as an unexpected systemic Stage11 exception
  and stopped the entire bulk run

This is a generic malformed-external-subtitle boundary defect, not a
HAWA-345-specific rule.

Generic fix:

- `build_external_ja_adapter()` now catches
  `HybridEvidenceValidationError` while constructing immutable external
  Hybrid evidence
- it maps the error to `ExternalSubtitleValidationError`
- the existing Stage11 route selector then conservatively rejects the bad
  external subtitle and continues as `ASR_ONLY`

Validation after the fix:

- `git diff --check`: PASS
- Python compile: PASS
- Stage11 live-adapter smoke: PASS
- Stage11 controller smoke: 46 PASS
- Stage12 batch smoke: PASS
- Stage12 bulk-runner smoke: PASS
- production HAWA-345 route-only replay:
  - `ROUTE=ASR_ONLY`
  - `EXTERNAL_OUTCOME=VALIDATION_FAILURE`
  - `ALIGNMENT_OUTCOME=NOT_ATTEMPTED`

No title/DVD-specific production branch was added.

HAWA-345 has durable baseline ASR and targeted second evidence but no
first-pass staging, CLEAN subtitle, controller report, Stage12 GENERATED
state, publication, or Jellyfin update.

Explicit `RUNNING -> PENDING` crash recovery is required before resuming
ordinary bulk processing.

### 2026-09-19 crash recovery completed

After confirming the old bulk PID was dead, HAWA-345 was the only active
rollout title, no GENERATED state existed, no Stage11 CLEAN/report existed,
and the canonical NAS Korean subtitle destination was absent,
`Stage12RolloutStateStore.recover_running("HAWA-345")` was executed.

Post-recovery durable state:

- HAWA-345: PENDING
- PENDING: 105
- PUBLISHED: 63
- FAILED_RETRYABLE: 4
- UNRESOLVED: 1
- RUNNING/GENERATED: 0

The four FAILED_RETRYABLE titles remain excluded from ordinary PENDING bulk
selection and will be handled separately after the ordinary PENDING queue.

## 2026-09-23 — Stage12 bulk complete and failure forensic

The formal Stage12 bulk live run completed normally. This is the latest
authoritative production state and supersedes earlier pending-count and
next-operation notes in this handoff:

- `STAGE12_BULK_LIVE=COMPLETE`
- `PROCESSED_THIS_RUN=28`
- final rollout: `PUBLISHED=152`, `FAILED_RETRYABLE=20`, `UNRESOLVED=1`,
  `PENDING=0`
- final publications, including `VEC-737` and `VEMA-246`, completed normally

A read-only forensic pass compared the rollout DB events and provenance,
existing bulk logs, local artifacts/staging, and current repository code.
No rollout state, retry, recovery, live execution, NAS/Jellyfin write, or
source change was made during that pass.

### FAILED_RETRYABLE — ASR audio timeline validation (9)

Titles:

- `HMN-899`
- `NHDTC-250`
- `PRED-889`
- `SGKI-075`
- `SGKI-106`
- `SNOS-334`
- `SVFLA-014`
- `SW-216`
- `NIMA-059`

Exact recorded failures:

- Eight titles: `ASRAudioValidationError: audio frame timestamp has an unsafe
  discontinuity`
- `NIMA-059`: `ASRAudioValidationError: resampler output cannot reconcile to
  source end`

The point at which the iterator failed varied by title. Remote ASR call
history for the failed titles was:

- zero calls: `HMN-899`, `PRED-889`, `SGKI-075`, `SGKI-106`, `SNOS-334`,
  `SW-216`
- six earlier 600-second chunks had already been sent for `NHDTC-250`
- fifteen earlier chunks had already been sent for `SVFLA-014`
- ten full chunks had already been sent for `NIMA-059`; its final partial
  chunk was not yielded because the iterator rejected the EOF/source-end
  reconciliation

The iterator exception happens while preparing the next chunk, so prior
yielded chunks can already have crossed Remote ASR before a later timeline or
EOF error. Typed `ASRAudioError` failures remain isolated to individual
titles; they no longer stop the batch.

### Generic decoded-sample-clock correction

Implemented in `teddy_discovery_asr_audio.py`; this section supersedes the
earlier trigger-pair-only replay note below:

- The first decoded frame timestamp anchors the output timeline unchanged.
- Later frames are checked against the exact cumulative decoded-sample clock.
  Strictly duplicate/backward raw PTS fail closed.
- Bounded timestamp jitter/overlap is corrected by moving the canonical frame
  start to the decoded sample clock. Per-frame correction is limited to one
  preceding decoded-frame duration. The absolute **peak signed net offset** is
  limited to three adjacent decoded-frame durations (64 ms for 1024-sample AAC
  at 48 kHz).
- A forward deviation larger than the existing timestamp tolerance stays a
  segment boundary: flush the old resampler and preserve the exact interval as
  silence. It is not absorbed into timestamp correction.
- Raw PTS, sample-clock expected PTS, per-frame correction, current signed
  offset, peak absolute net offset, one-second window net/absolute correction,
  lifetime absolute correction, preserved gap count/duration, overlap count,
  EOF output counts, and fail-closed reason are structured diagnostics.
- EOF still requires resampled output to reconcile within one 16 kHz sample
  of the corrected source end. No decoded audio samples are dropped or
  duplicated, and the existing absolute chunk/sample boundaries remain in
  force.

Lifetime absolute correction remains a diagnostic only. It is not a production
reject criterion because long alternating ±1-tick timestamp jitter in the
already-PUBLISHED 44.1 kHz control `SIRO-4448` produced 2,253 tiny corrections
totalling 102.177 ms while its signed EOF drift was zero and peak net offset
was only 22.676 µs. The old lifetime-sum guard incorrectly rejected it. The
three-frame peak bound remains unchanged; it now rejects sustained same-way
timeline movement while allowing that zero-mean jitter.

### Full-media read-only replay — 2026-09-23

Replayed all nine failed titles, the three previously used PUBLISHED controls,
and ten additional PUBLISHED controls selected by source-size quantiles from
the rollout DB (bounded selection; no NAS-wide scan). Each source path, size,
and mtime matched the rollout row before replay. Production iterator/decode,
resample and chunking ran to EOF; failed titles also received an in-memory
diagnostic continuation to EOF after their exact production fail point. That
continuation does not change the production decision or validator bound. Each
source SHA-256 was recorded; the source copy used the dedicated
`/var/tmp/teddy-stage11-asr-replay` directory, and every title cleanup was
verified empty before checking `df -h /var/tmp` and `free -h` and starting the
next. `/tmp` was not used for media. Forward gaps are counted as gaps and
preserve silence. The following values are in seconds unless marked otherwise;
`window` is the maximum correction within the one-second diagnostic window.

| DVD-ID | Production | Full decoded frames | Overlap events / lifetime absolute | Max single correction | EOF signed / peak net | 1s window net / absolute | Forward gaps: count / duration / max | EOF expected → resampled (mismatch) | Production fail point |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| HMN-899 | FAIL | 400,294 | 60,222 / 20.218 s | 0.667 ms | +20.218 s / 20.218 s | 3.667 / 3.667 ms | 30,655 / 20.218 s / 0.667 ms | 136,957,179 → 136,957,178 (−1) | frame 1,690, PTS 1,730,560; peak net > 3 frames |
| NHDTC-250 | PASS | 515,004 | 2 / 20.229 ms | 19.542 ms | +20.229 / 20.229 ms | 19.542 / 19.542 ms | 2,747 / 157.944 s / 63.854 ms | 178,315,129 → 178,315,129 (0) | — |
| PRED-889 | FAIL | 344,708 | 53,649 / 17.942 s | 0.667 ms | +17.942 s / 17.942 s | 3.667 / 3.667 ms | 29,474 / 125.508 s / 64 ms | 119,668,464 → 119,668,464 (0) | frame 1,780, PTS 1,847,728; peak net > 3 frames |
| SGKI-075 | FAIL | 408,245 | 60,210 / 21.554 s | 0.667 ms | +21.554 s / 21.554 s | 3.667 / 3.667 ms | 36,643 / 21.554 s / 0.667 ms | 139,692,491 → 139,692,490 (−1) | frame 1,275, PTS 1,305,616; peak net > 3 frames |
| SGKI-106 | FAIL | 378,701 | 59,639 / 20.141 s | 0.667 ms | +20.141 s / 20.141 s | 3.333 / 3.333 ms | 33,670 / 138.342 s / 64 ms | 131,476,752 → 131,476,752 (0) | frame 1,294, PTS 1,341,904; peak net > 3 frames |
| SNOS-334 | FAIL | 448,855 | 18,783 / 12.322 s | 0.667 ms | +12.322 s / 12.322 s | 2.333 / 2.333 ms | 38,121 / 65.460 s / 33.333 ms | 154,256,541 → 154,256,541 (0) | frame 2,323, PTS 2,390,035; peak net > 3 frames |
| SVFLA-014 | FAIL | 726,376 | 5 / 92.958 ms | 21.313 ms | +92.958 / 92.958 ms | 92.958 / 92.958 ms | 3,874 / 220.370 s / 63.5 ms | 251,462,257 → 251,462,257 (0) | frame 423,389, PTS 439,850,641; peak net > 3 frames |
| SW-216 | FAIL | 363,276 | 6,523 / 63.779 s | 21.313 ms | +63.738 s / 63.738 s | 65.75 / 65.75 ms | 8,094 / 164.979 s / 91.313 ms | 126,637,870 → 126,637,869 (−1) | frame 438, PTS 457,093; signed peak 66.292 ms exceeds 64 ms |
| NIMA-059 | FAIL | 298,090 | 4,763 / 99.229 ms | 20.833 µs | +99.229 / 99.229 ms | 41.667 / 41.667 µs | 2 / 156 ms / 92 ms | 101,750,549 → 101,750,549 (0) | frame 192,407, PTS 197,029,183; peak net > 3 frames |

The eight Group A files and NIMA still exceed the generic three-frame peak
bound over their full timelines; their production errors remain
`ASRAudioValidationError` and title-scoped. `NHDTC-250` is the only one of the
nine that passes full production replay. In SW-216, units matter: the early
production crossing is 66.292 ms, while the EOF diagnostic net offset is
63.738 **seconds**, not milliseconds.

All 13 PUBLISHED controls passed full replay with EOF mismatch of 0 or −1
sample. Twelve had zero canonicalized overlap and zero net/peak drift. The
exception, `SIRO-4448`, had the 2,253 tiny alternating corrections described
above and still passed with zero signed EOF drift. The controls covered both
forward-gap and no-gap sources. The additional bounded cohort was
`FC2-PPV-4660439`, `FC2-PPV-4640215`, `SNOS-120`, `SIRO-5537`, `MNGS-076`,
`FCT-201`, `DOKI-037`, `FNS-237`, `DOKS-689`, and `NHDTA-663`; all decoded AAC
at 48 kHz. Existing controls add both 44.1 kHz (`SIRO-4448`) and 48 kHz
(`FC2-PPV-4575470`, `FC2-PPV-4551303`). Existing controls included both short
and long files, and forward gaps ranged from none to 2940 events / 172.481 s.
The ten added controls each had zero overlap corrections; they exercised
forward-gap preservation and EOF/resampler accounting.

Regression validation passed: long alternating ±1-tick jitter, sustained
same-direction drift fail, per-frame unsafe overlap fail, duplicate/backward
PTS fail, forward-gap silence preservation, EOF mismatch fail, chunk boundary
regressions, ASR audio/source/remote/transcriber smokes, Stage11 controller/
live-adapter/deployment smokes, Stage12 batch/bulk-runner/rollout smokes,
Python compile, and `git diff --check`. No retry, live ASR/Whisper call, rollout
state change, NAS/Jellyfin write, remux, or transcode occurred.

Canary candidate among these nine: `NHDTC-250` only. It passed complete
production replay with two bounded overlap corrections, 2,747 forward gaps
preserved as silence, and exact EOF sample reconciliation. This is a replay
result, not a canary execution or retry approval.

### FAILED_RETRYABLE — Jellyfin external Korean subtitle recognition (6)

Titles:

- `FC2-PPV-4758058`
- `FC2-PPV-4973050`
- `MKON-126`
- `NHDTB-93803`
- `SDDE-763`
- `START-636`

Exact final failure for all six:
`Stage12BatchTitleError: Jellyfin external Korean subtitle not recognized`.
Each transitioned `RUNNING -> GENERATED -> FAILED_RETRYABLE`; Stage11 passed,
the generated artifact was validated, and publication recorded an atomic,
verified destination with its SHA-256. Read-only SHA-256 checks confirmed the
local `clean-ko-v1.srt` and controller report files still match the hashes
stored in rollout state.

The repository already has a Jellyfin refresh fallback, including full
refresh, but these attempts still ended in recognition failure after that
fallback. The artifact/report pair remains available and hash-matched, so it
may be reused only after the existing provenance/source checks pass. Inspect
the exact Jellyfin item/path and external subtitle stream state before another
recognition attempt.

- current-code root-cause status: **NOT RESOLVED**
- next action: **FIX_FIRST** — read-only item/path/stream reconciliation;
  preserve the verified artifacts for eligible reuse

### FAILED_RETRYABLE — semantic output validation retry exhausted (5)

Titles and failed part indexes:

- `FNS-235` — part 7
- `GDTM-091` — part 12
- `HMN-896` — part 5
- `MAAN-1193` — part 9
- `SCOP-830` — part 3

Exact final exception for each:
`StatefulSemanticOutputValidationRetryExhausted: semantic output validation
retry exhausted`; all recorded `attempts=2`, `max_attempts=2`. These failed
during semantic validation, before clean artifact acceptance/publication.
The DB/bulk evidence records the exhausted retry and part index; it does not
preserve a more specific validator message per title.

- current-code root-cause status: **NOT RESOLVED**
- next action: **MANUAL_REVIEW** — inspect rejected part output and its
  validation reason before choosing any targeted input/data correction or
  retry

### UNRESOLVED — JUR-750

`JUR-750` was already `UNRESOLVED` during `INITIALIZE_FROM_INVENTORY`, with
`SUBTITLE_INVENTORY_INVALID`; it has no execution history. The associated
noncanonical sidecar is `JUR-750.R6B2-Clean.ko.srt`.

- current-code root-cause status: **NOT RESOLVED**
- next action: **MANUAL_REVIEW** — decide explicitly how to handle the
  noncanonical sidecar before inventory resolution
- do not automatically rename, delete, or overwrite the sidecar

### Next Stage12 operation

Start with read-only forensic reconciliation of the six Jellyfin recognition
failures: verify each exact Jellyfin item/path and external subtitle stream,
then establish whether the existing hash-verified artifact can be reused.
Do not run retry/recovery or write to NAS/Jellyfin until the forensic result
supports a separately authorized operation. Keep the nine ASR failures and
five semantic failures out of blind retry; handle them using the actions above.

## Stage12 delayed Jellyfin indexing and publication reconciliation

The follow-up read-only Jellyfin forensic confirmed five prior recognition
failures already have the exact published sidecar visible in Jellyfin:

- `FC2-PPV-4758058`
- `FC2-PPV-4973050`
- `MKON-126`
- `NHDTB-93803`
- `SDDE-763`

For those five, current NAS sidecar, recorded publication SHA/provenance,
Jellyfin exact item path, external stream path, Korean language, and `subrip`
codec agree. The evidence supports delayed Jellyfin indexing as the common
false-negative: the original bounded polling window ended before the stream
appeared. There is no evidence for a shared filename, path, or SRT defect.
`START-636` remains different: its exact external Korean stream was absent at
the read-only check and must stay `FAILED_RETRYABLE` unless a later exact GET
proves recognition. Do not add a title-specific workaround.

The generic recognizer retains the item-specific Default refresh followed by
FullRefresh, but accepts a separate bounded `full_refresh_max_attempts` window.
The bulk runner allows 42 full-refresh polls at its existing 5-second cadence
(up to 205 seconds for that phase), while keeping the default-refresh window
unchanged. A visible stream is accepted only for the exact media item and
sidecar path, Korean language, external status, and `subrip` codec. If the
stream never appears, the existing title failure path remains in force.

Added `teddy_discovery_stage12_reconcile.py` as a separate, explicit one-title
reconciliation path. It does not regenerate Stage11 output, republish, write
NAS, or refresh Jellyfin. Before the rollout state can be reconciled, it
revalidates current Discovery and NAS source identity/fingerprint, the full
Stage11 baseline/CLEAN/report provenance, immutable publication event proof,
destination bytes and SHA-256, and exact Jellyfin item/stream evidence using
GET requests only. The only state write is the existing audited
`FAILED_RETRYABLE -> PUBLISHED` reconciliation after every check passes. The
bulk runner exposes this path only as explicit `--mode reconcile --dvd-id`
and requires `TEDDY_STAGE12_PUBLICATION_RECONCILE_AUTHORIZED` to be set to the
review token. No production reconciliation was run in this change; the five
titles were pending separate approval at the time of this implementation
commit. `START-636` cannot pass the stream-presence gate while its exact
stream is absent.

Smoke coverage:

- delayed visibility after FullRefresh succeeds within the added bounded
  polling window;
- permanently absent, wrong-path, wrong-language, non-external, and wrong
  codec streams are rejected;
- reconciliation rejects NAS SHA, source identity, and publication
  provenance mismatch without changing state;
- exact valid existing publication evidence reconciles in an isolated
  temporary fixture without Jellyfin writes;
- Stage12 batch, bulk runner, rollout, and reconciliation smoke tests pass;
- changed modules compile and `git diff --check` passes.

At the time of this implementation update, the next operation was one
explicit reconciliation per eligible title after separate review. Subsequent
production results are recorded below. Do not include `START-636` unless its
exact stream becomes visible. If it remains absent, use a dedicated read-only
scanner diagnostic to compare the exact item's library path and refresh/scan
visibility; leave rollout state unchanged until evidence proves the expected
stream exists.

## Stage12 production reconciliation canary — 2026-09-23

Ran one explicitly authorized reconciliation for `FC2-PPV-4758058` using
code HEAD `d18dd5ecde8743c8c780ddd4eaf9a4a493aec7cc`. Before execution, HEAD
matched exactly, the worktree was clean, and the title was
`FAILED_RETRYABLE`, transition sequence 4, with reason
`STAGE12_TITLE_FAILURE`. The targeted reconcile coordinator returned PASS:
`RECONCILIATION_RESULT=PUBLISHED`, reason `PUBLICATION_RECONCILED`.

Fresh evidence matched at reconciliation time:

- Canonical Discovery source path was
  `FC2-PPV/FC2-PPV-4758058/FC2-PPV-4758058.mp4`; source size and nanosecond
  mtime matched rollout state and NAS read-only `lstat`.
- Existing Stage11 CLEAN/report/baseline bundle passed provenance validation;
  CLEAN SHA-256 was
  `359c7293b4b1a8c6c11a640ee4834020fe6f0b7cbe48dd7aada4c1739b5aacf5`, and
  report SHA-256 matched recorded state.
- NAS destination
  `FC2-PPV/FC2-PPV-4758058/FC2-PPV-4758058.ko.srt` was read-only verified at
  1,908 bytes. Its SHA-256 matched both the Stage11 artifact and immutable
  publication proof.
- Jellyfin GET resolved item `f572f98325049203905b21a25a427aba` at the exact
  expected media path and reported the exact sidecar as an external `kor`,
  `subrip` subtitle stream.
- The reconciliation event records `controller_call_performed=false` and
  `nas_write_performed=false`; the code path used Jellyfin GET only and made
  no refresh/write request. No Stage11 rerun, translation, or republication
  occurred.

Afterward, only this title had a new rollout event: sequence 5,
`FAILED_RETRYABLE -> PUBLISHED`, reason `PUBLICATION_RECONCILED`. Final
rollout counts are `PUBLISHED=153`, `FAILED_RETRYABLE=19`,
`UNRESOLVED=1`, `PENDING=0`. `START-636` was not touched.

## Stage12 remaining Jellyfin reconciliation titles — 2026-09-23

After the canary passed, independently revalidated and reconciled the other
four forensic-approved titles. Each title was gated on its current
`FAILED_RETRYABLE` state, canonical Discovery source identity and NAS source
fingerprint, Stage11 baseline/CLEAN/report provenance, immutable publication
proof, NAS destination bytes/SHA, and a fresh Jellyfin GET for the exact item
and exact external KO stream (`Language=kor`, `IsExternal=true`,
`Codec=subrip`, exact expected sidecar path). All four passed. Each moved from
sequence 4 `FAILED_RETRYABLE` / `STAGE12_TITLE_FAILURE` to sequence 5
`PUBLISHED` / `PUBLICATION_RECONCILED`.

| DVD-ID | NAS sidecar bytes / SHA-256 | Jellyfin item ID |
| --- | ---: | --- |
| `FC2-PPV-4973050` | 795 / `0eab564e9a01ee5e70e61a4e05076b41861d4d7ab0a4d014b55fa16b6eb2a380` | `38558e5c4604af22e39557fe8b699d40` |
| `MKON-126` | 18,607 / `288b16e92029a6f22e974d9e4c625703afaa8e593a17b76887b7c5381269bace` | `db6af239d58cab308da599eaba297cba` |
| `NHDTB-93803` | 68 / `28676cd94f390ef965a8557512332c7a3d9ece65a9d6838f3c9c3ecdaa5e328f` | `d83183871bf60382367b987172d60c77` |
| `SDDE-763` | 42,342 / `bfe384e976f0311144804f099ed06f106820fcbe019ba792cfddc5dda057d8e9` | `9c9b380e38b05f9ae20fa5acd9ae808f` |

For every title, the local CLEAN SHA matched the report/provenance and the
read-only NAS destination SHA; the Jellyfin item and stream paths matched the
expected media and `.ko.srt` paths. Reconciliation used no controller call,
NAS write, or Jellyfin refresh/write. No Stage11 rerun, translation, or
republication occurred. The four appended rollout events are event IDs
724–727 and apply only to these four DVD-IDs. `START-636` remains
`FAILED_RETRYABLE` and was not touched.

Final rollout counts after the four-title sequence are `PUBLISHED=157`,
`FAILED_RETRYABLE=15`, `UNRESOLVED=1`, `PENDING=0`. Together with the earlier
canary, the complete five-title delayed-indexing group is reconciled; all
other rollout titles remain unchanged.

## START-636 delayed Jellyfin indexing diagnostic and reconciliation — 2026-09-23

The exact `START-636` Jellyfin item received one item-specific Default refresh
as a separate bounded diagnostic. The expected external Korean stream first
appeared on the second post-refresh PlaybackInfo poll, about 5.2 seconds after
the refresh. Its metadata was `Language=kor`, `IsExternal=true`,
`Codec=subrip`, and exact path
`/media/adult/START/START-636/START-636.ko.srt`; the item was
`157b376a8917d59c87de7b6ee5c01ec7` at
`/media/adult/START/START-636/START-636.mp4`. The stream appeared during the
Default polling window, so no FullRefresh was issued. This confirms delayed
Jellyfin indexing for the remaining title; no filename or sidecar workaround
was needed.

Then, using code HEAD `3155d1a455baa3753d5bf65271c6fb7089b874eb`, ran the
existing explicit one-title `--mode reconcile --dvd-id START-636` path. Before
execution, HEAD matched, the worktree was clean, and current read-only checks
confirmed `FAILED_RETRYABLE`, sequence 4, reason `STAGE12_TITLE_FAILURE`.
Discovery and NAS source identity matched at
`START/START-636/START-636.mp4` (1,801,037,186 bytes; mtime
1788861288542183653 ns). The existing Stage11 artifact/report bundle passed
provenance validation: CLEAN SHA-256
`e2400ea07c0a7f2b90885d6de2bf6231fffdafef20c61ceba236770b9cf2f629`, report
SHA-256 `fbe6e0390812bae89c51c98c19d7bf14777c41dedecf203101f7a9da8c9a0e6c`.
NAS sidecar `START/START-636/START-636.ko.srt` was 364 bytes; its read-only
SHA-256 matched both the CLEAN artifact and verified publication proof.
Jellyfin GET reconfirmed the exact item and stream metadata above.

Reconciliation passed: only `START-636` changed from sequence 4
`FAILED_RETRYABLE` / `STAGE12_TITLE_FAILURE` to sequence 5 `PUBLISHED` /
`PUBLICATION_RECONCILED` (event 728). The audited event records
`controller_call_performed=false` and `nas_write_performed=false`; reconciliation
used Jellyfin GET only and issued no refresh. No Stage11 rerun, translation,
republication, NAS write, or direct Jellyfin DB write occurred. A full
before/after snapshot of every other rollout title's status, sequence, and
reason was identical.

Final rollout counts are `PUBLISHED=158`, `FAILED_RETRYABLE=14`,
`UNRESOLVED=1`, `PENDING=0`. The separate diagnostic's one exact-item Default
refresh is recorded above; it did not alter rollout state or write the NAS
sidecar.

## Stage12 explicit FAILED_RETRYABLE retry path — 2026-09-23

Added `teddy_discovery_stage12_bulk_runner.py --mode retry` as a generic,
operator-authorized single-title path from `FAILED_RETRYABLE` through the
existing Stage11 controller, Stage12 artifact validation/publication, and
Jellyfin external-stream check. This path is separate from ordinary bulk
`live` selection and publication-only `reconcile`.

The retry command requires exactly one `--dvd-id`, a positive
`--expected-sequence`, exact `--expected-head`, a clean worktree, and the
separate `TEDDY_STAGE12_EXPLICIT_RETRY_AUTHORIZED=YES_I_HAVE_REVIEWED_THE_SINGLE_TITLE`
authorization. It fails closed on active RUNNING/GENERATED rollout state,
state/sequence mismatch, Discovery or NAS source fingerprint drift, existing
destination, inconsistent event history, or recorded artifact/publication
provenance. The durable transition is directly
`FAILED_RETRYABLE -> RUNNING`, reason `STAGE12_EXPLICIT_RETRY_START`, with the
authorized sequence recorded in event provenance; the database update is
sequence-guarded. Retry execution uses the normal `Stage12BatchRunner._run_one`
path with immutable one-title selection. Any title failure follows the
existing Stage12 failure classification; retryable failures return to
`FAILED_RETRYABLE`, while existing terminal safety conflicts retain their
terminal handling.

No production retry was run while implementing this path. Read-only rollout
state still showed `NHDTC-250=FAILED_RETRYABLE`, sequence 3,
`STAGE12_TITLE_FAILURE`, source size 6,618,791,523 bytes, and source mtime
1788879891350125554 ns. Rollout counts were `PUBLISHED=158`,
`FAILED_RETRYABLE=14`, `UNRESOLVED=1`.

Offline retry smoke passed: exact one-title selection, missing/duplicate
selector rejection, absent authorization, status/sequence/fingerprint and
artifact-provenance guards, title failure isolation, normal Stage11 and
publication path reuse, and unchanged other-title state. Existing Stage12
batch, bulk-runner, rollout, and reconciliation smokes also passed; compile
and `git diff --check` passed. The retry command shape for the later NHDTC-250
canary is:

```sh
TEDDY_STAGE12_EXPLICIT_RETRY_AUTHORIZED=YES_I_HAVE_REVIEWED_THE_SINGLE_TITLE \
  python3 /opt/missav-pwa-subtitle-stage11/teddy_discovery_stage12_bulk_runner.py \
  --mode retry --batch-size 1 --max-titles 1 \
  --dvd-id NHDTC-250 --expected-sequence 3 \
  --expected-head <exact-clean-authorized-HEAD>
```

Replace the HEAD value only after checking the exact clean code revision at
execution time. This command has not been run.

## Production ASR media temp storage — 2026-09-23

The CT108 tmpfs incident was traced to the production Stage11 factory creating
`ASRMediaSourceReader` without `temp_root`; `tempfile.mkdtemp(dir=None)` then
resolved to `/tmp`. A 6,618,791,523-byte source could be fully copied there,
contributing to RAM/swap exhaustion and an SSH outage. No production retry or
media copy was run for this fix.

The shared Stage11 deployment config now injects
`/var/tmp/teddy-stage11-asr-production` with disk-backed filesystem validation
for both ordinary Stage12 bulk and explicit retry. The reader rejects `/tmp`,
symlinked/non-private/unwritable roots, and non-disk filesystem types without
fallback. After remote source stat, preflight requires
`source_size_bytes + 4 GiB` free. A single-source bound is sufficient because
the Stage12 runner lock excludes competing bulk/retry runs, batch execution is
serial, and the baseline transcriber cleans its source in `finally` before the
controller can invoke the targeted adapter; targeted evidence uses its own
context-managed copy afterward.

Partial transfer catches `BaseException`, aborts the transfer child, removes
only that request's media file/directory, and re-raises the primary failure.
Normal baseline/targeted use cleans the same per-request directory. Cleanup
outcome, temp-root resolution, source size, free bytes, required bytes, and
request-directory basename are logged. Existing source identity and mtime
checks are unchanged.

Tiny-payload temp policy smoke passed root creation/permissions, free-space
pass/fail, sibling-directory preservation, sequential baseline/targeted
lifecycle, and partial-copy cleanup for `Exception`, `KeyboardInterrupt`, and
`SystemExit`. ASR source/audio/transcriber, Stage11 adapter/controller/
deployment, Stage12 retry/batch/bulk/rollout/reconciliation smokes, compile,
and `git diff --check` all passed. No large media fixture, Remote ASR, Whisper,
rollout mutation, or NAS/Jellyfin write was used.
