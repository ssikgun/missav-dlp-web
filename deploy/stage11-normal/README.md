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

## On-demand Whisper worker lifecycle

Whisper is intentionally idle when no ASR request is running. There is no
persistent Whisper service and no system-start worker. Full-title baseline ASR
and targeted speech evidence share the existing bounded VM122 transport. The
full-title adapter verifies the current source snapshot and copies media into
its protected temporary area before the first chunk request can start the SSH
tunnel and worker. Targeted ASR likewise copies and verifies media before its
first request. Each ASR phase stops and verifies only the worker and tunnel it
started; temporary media is cleaned before that stop. Hermes review runs after
full-title ASR cleanup. An unverified remote stop is a failure, not successful
cleanup.

The established VM122 profile and GPU floors remain unchanged: large-v3,
CUDA/int8_float16, 3,500 MiB start floor, and 1,500 MiB runtime floor. The
existing full-title worker/request limits remain in force; no automatic retry
or worker restart is performed. The historical successful full-title run used
the existing 900-second worker/request limit, but its total wall time was not
recorded. A worker reaching its limit therefore fails the current ASR phase
safely; it does not continue automatically.

The process reads its worker connection values from the permanent, private
configuration file
`/opt/missav-dlp-web/discovery/stage11-normal-deployment/targeted-asr-worker.json`.
It must be owned by the service's effective user and mode `0600`, in a
non-symlinked directory chain that is not group- or world-writable. Its exact
JSON keys are `remote_repo_root`, `remote_source_sha`, `ssh_key`,
`known_hosts`, `remote_python`, `model_cache_root`, and `model_snapshot`.
The deployment preflight checks VM122 SSH on port 22, validates this local
configuration and SSH identity, then uses the configured virtualenv for a
read-only repository and model-snapshot check. It does not require a listener on
8091, start a worker, load a model, query GPU or the local LLM API, or create files. It reports
that the idle worker is expected. NAS, Hermes, Jellyfin, and SubtitleCat
connectivity checks remain in place.

No configuration file or secret is created or shipped by this source change.
On the real CT108 only, an operator must confirm every exact VM122 path and
source SHA from the live runtime, create the JSON with the service's effective
owner and mode `0600`, then run the read-only deployment preflight. Full-title
or targeted ASR stops safely until this configuration and remote preflight pass.

One-title regeneration independently reuses each valid source-bound ASR or
Japanese subtitle cache when supplied. An absent cache or one that fails its
SHA/source validation is not reused: the existing Normal Mode baseline ASR or
external Japanese subtitle discovery/download path acquires that input into a
new private run. Unsafe file ownership, links, modes, and output collisions
still stop the run. Existing Korean subtitles are never inputs. The ordinary
new-holding queue continues to acquire baseline ASR and external Japanese
evidence through the same Normal Mode path. Existing published/history rows
are not automatically re-enqueued for regeneration.

### Update both ends of the on-demand worker

The VM122 launcher reads the single active model ID from local port 8082 and
checks that it stays stable for the owned worker's lifetime. A model change or an
unverifiable API response stops that worker. Model names do not affect eligibility.

1. Prepare a new independent VM122 checkout under the worker user's home.
   Use the canonical origin and branch `teddy-subtitle-stage11`, keep that
   branch checked out, and verify the approved exact HEAD, repository root
   and clean state. Retain the previous checkout and configuration.
2. On VM122, from that checkout, use the existing configured virtualenv and
   run the command below with the verified configuration values. Run this
   readiness check before copying a full video. It checks current VRAM and
   model identity without starting Whisper. Release preparation uses a
   different idle preflight and does not require this point-in-time VRAM gate.

   ```bash
   "$remote_python" -B teddy_discovery_asr_int8_ephemeral_launcher.py check \
     --cache-root "$model_cache_root" --snapshot "$model_snapshot" \
     --min-free-vram-mib 3500
   ```

3. In an approved CT108 maintenance window with no Stage11 work active, retain
   a private 0600 copy of the current worker JSON. Stage an owner-private 0600
   replacement in the same directory with only `remote_repo_root` and
   `remote_source_sha` updated to the verified VM122 checkout and commit.
   Validate it with `BoundedASRWorkerConfig.load` and
   `BoundedTargetedASRTransport.read_only_preflight()` using the staged path,
   then atomically install the validated file. Keep SSH, Python, and model
   snapshot settings from the existing verified configuration.
4. From a clean checkout pinned to the approved new SHA, check the existing
   rollout DB schema read-only before invoking
   `bash deploy/stage11-normal/deploy.sh prepare "$approved_sha"`. The
   prepare action leaves current and the timer in place. Verify the prepared
   HEAD and Stage12 preflight log.
5. If preparation fails, restore the saved JSON atomically so it again points
   to the old VM122 checkout and SHA. Keep the existing CT108 release
   `29b8be26a10e3e5dbab7802f09995ab108a40a6f` and both VM122 checkouts.
