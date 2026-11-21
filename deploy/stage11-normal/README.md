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

Prepare a permanent, clean release from the canonical GitHub branch without
changing `current`, installing units, or enabling the timer:

```sh
bash deploy/stage11-normal/deploy.sh prepare COMMIT_SHA
```

The release is independently cloned under the deployment's permanent
`releases/` directory, checked out at the exact SHA, checked for a clean
worktree and canonical origin, and passed through the existing read-only
Stage12 preflight. A conflicting or incomplete preparation directory is kept
for inspection and blocks replacement.

After a separate operator decision, switch `current` and install the unit
files while requiring the timer to remain disabled and inactive:

```sh
bash deploy/stage11-normal/deploy.sh switch-current COMMIT_SHA
```

Timer activation is a separate explicit command:

```sh
bash deploy/stage11-normal/deploy.sh activate-timer COMMIT_SHA
```

The legacy one-command deployment remains available and performs all three
steps in order, including timer activation:

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

## Targeted Whisper worker lifecycle

Normal Mode and the one-title regeneration dependencies use the same bounded
transport for **targeted** speech evidence. The adapter verifies the current
source snapshot, copies the media into its protected temporary area, then
starts the SSH tunnel and VM122 worker only when the first targeted ASR request
is made. The worker and owned tunnel are cleaned up after the targeted pass and
temporary-media context exit. An unverified remote stop is a failure, not a
successful cleanup. The existing start/runtime GPU floors are 3,500/1,500 MiB
and the worker lifetime and individual request are capped at 900 seconds; the
Whisper model/runtime profile is unchanged.

The process reads its worker connection values from the permanent, private
configuration file
`/opt/missav-dlp-web/discovery/stage11-normal-deployment/targeted-asr-worker.json`.
It must be owned by the service's effective user and mode `0600`, in a
non-symlinked directory chain that is not group- or world-writable. Its exact
JSON keys are `remote_repo_root`, `remote_source_sha`, `ssh_key`,
`known_hosts`, `remote_python`, `model_cache_root`, and `model_snapshot`.
The remote repository identity is checked against the canonical Stage11 branch,
origin, configured commit and a clean worktree before the launcher starts.
No configuration file or secret is created or shipped by this source change;
targeted ASR stops safely until an operator provisions and verifies this file.

This bounded lifecycle covers **targeted** evidence calls. The existing
full-title baseline transcriber remains on its separately configured ASR
endpoint and is not converted to this 900-second ephemeral worker by this
change. One-title regeneration still requires an existing source-bound ASR
artifact and Japanese subtitle; it stops before creating its output root when
either input is missing or mismatched. The ordinary new-holding queue continues
to acquire its baseline and Japanese source through the existing Normal Mode
path. Existing published/history rows are not automatically re-enqueued for
regeneration.
