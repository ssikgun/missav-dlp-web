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

For an explicitly paused deployment that must not enable or start the timer,
use:

```sh
bash deploy/stage11-normal/deploy.sh --paused COMMIT_SHA
```

Paused mode requires the Normal timer to be `disabled/inactive` and the Normal
service to be `inactive`. It snapshots and checksums the current release,
`runtime.env` and both systemd units before preflight. It repeats the paused
state checks after preflight, immediately before switching `current`, after
installing runtime settings and units, and after `daemon-reload`. Any failure
after the pointer switch attempts a paused restore without starting a unit.

Use only the backup from that paused deployment for its rollback:

```sh
bash deploy/stage11-normal/rollback.sh --paused BACKUP_DIRECTORY
```

Paused rollback verifies the backup identity and checksums, restores the exact
saved release pointer, `runtime.env` and unit files, and verifies that the
timer remains `disabled/inactive` and the service `inactive`. A corrupt or
non-paused backup is rejected. Commands without `--paused` retain the existing
live deployment and saved timer-state rollback behavior.

Rollback while the subtitle service is inactive with:

```sh
bash deploy/stage11-normal/rollback.sh BACKUP_DIRECTORY
```

Rollback restores the prior unit/release/timer state. It retains generated
artifacts and queue history, and never edits existing subtitles. Web,
completion, writer and GPU Worker units are outside this deployment.
