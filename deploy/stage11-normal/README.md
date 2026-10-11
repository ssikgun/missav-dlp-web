# Stage11 Normal Mode deployment

`USER_INTERVENTION=0`. New current canonical holdings enter the existing
Stage12 inventory/state machine, at most four per cycle. The native queue
processes one ordinary PENDING title per cycle with the existing title lock,
NAS no-overwrite publisher and Jellyfin recognition. Existing historical,
failed and published rows are never reset. The timer runs 60 seconds after
activation and 300 seconds after the preceding service exits.

Normal Mode requires a source-bound baseline and accepted external JA/alignment.
It translates through the existing Hermes provider/model/reasoning using the
previously verified isolated, zero-tool native `chat -Q` path. Whole-title
translation uses strict identity, source-aware output and absorption validation;
the existing fixed-64 partition policy is the bounded fallback. Native turns
retain 600-second inactivity / 3600-second absolute timeouts and two output
validation attempts. An unavailable external JA, unresolved alignment or failed
core translation terminates with a durable error. There is no user approval
state. Service execution has a 24-hour cap and no automatic service restart.

Supplemental dialogue insertion is OFF because automatic Japanese/audio accuracy
has not been proven. Ambiguous evidence is skipped; no supplemental model or
manual listening is requested. Clear source metadata alone can be omitted.
Existing JA/KO files and historical evidence are preserved. Stage11 persists a
canonical SRT plus mechanical report and source/identity proof; Stage12 owns
publication. The legacy diagnostic/review APIs remain callable for offline
forensics and are outside normal operation.

Deploy an exact committed revision with:

```sh
bash deploy/stage11-normal/deploy.sh COMMIT_SHA
```

The script creates a clean detached release, runs the existing production
preflight, atomically pins `current` and `runtime.env`, then enables only the
new subtitle timer. Inspect `journalctl -u teddy-subtitle-normal.service` and
`/opt/missav-dlp-web/discovery/stage12-runtime/status.json`. Generated artifacts
are under `/opt/missav-dlp-web/discovery/stage11-normal-runtime-v1/artifacts`.

Rollback while the subtitle service is inactive with:

```sh
bash deploy/stage11-normal/rollback.sh BACKUP_DIRECTORY
```

Rollback restores the prior unit/release/timer state. It retains generated
artifacts and queue history, and never edits existing subtitles. Web,
completion, writer and GPU Worker units are outside this deployment.
