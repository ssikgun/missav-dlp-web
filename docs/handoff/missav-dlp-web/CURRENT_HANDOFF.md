# Teddy Downloader / missav-dlp-web — CURRENT HANDOFF

## 2026-09-29 Stage13-F2M-D8 — stopped on duplicate-notification retry gap (INCOMPLETE)

Initial repo state was expected HEAD `df8bec646f736855e975849bbd993db68f5bd19b`,
branch `teddy-subtitle-stage11`, clean worktree; `origin/teddy-subtitle-stage11`
matched. The success-invariant/reconciler implementation and deployment were
not started after source inspection confirmed the explicitly prohibited
crash/retry gap. No implementation smoke was run.

Production preconditions were rechecked GET/read-only: gate false, web `/login`
HTTP 200, completion timer/service and reconcile-apply inactive. The exact
operation remains `RECONCILE_PENDING`, `nas_delete_complete=1`,
`discovery_reconciled=1`, `jellyfin_reconciled=NULL`; holding 20 is present=0,
VEMA-246 present count=0, current JAV holdings=183. Jellyfin broad inventory
returned 364/364 with one exact path candidate and the old ID
`0fa5e1cd9743f9e30dc69054e1c12375`; API-key exact-ID query returned 0. No
Jellyfin notification was sent.

The concrete retry gap is in current source: `JellyfinDeleteReconciler.__call__`
calls `notify_deleted()` whenever the broad path lookup returns one candidate,
then polls the broad inventory. A timeout returns false. The recovery
`apply_operation()` returns `RECONCILE_PENDING` without persisting that the
notification was sent. A later retry again sees the broad candidate and calls
`notify_deleted()` again, even when the candidate's exact ID query would now
return zero. The existing provenance schema has only `jellyfin_reconciled` and
`result_state` for Jellyfin status; it has no durable notification-sent marker.

The offline recovery smoke's “crash after notification” case only models the
item already absent on retry, which avoids a POST. The timeout case confirms
the operation remains pending after one POST, but it does not retry while the
same exact ID is still live. That leaves the short-window duplicate-POST case
uncovered. Per the explicit stop condition, no schema expansion or workaround
was attempted and no source/test file changed.

Classification for the current exact item remains
`BROAD_INVENTORY_GHOST` (broad=1, exact-ID=0). The exact operation is not
finalized because implementation work stopped before a safe retry contract
could be designed and validated. Production mutation audit: Jellyfin 0,
provenance 0, NAS 0, Discovery 0, restart 0. Only this canonical handoff was
updated. Next: separately design a durable, idempotent notification/retry
contract before resuming the ghost-aware reconciler change; do not simply
repeat `notify_deleted()` when an earlier attempt may already have sent it.

## 2026-09-29 Stage13-F2M-D7 — broad-inventory ghost identified (READ-ONLY)

Initial repo state was expected HEAD `48acdb52abd4dbd30ed4694f09b0c3b98eea94c8`,
branch `teddy-subtitle-stage11`, clean worktree; `origin/teddy-subtitle-stage11`
matched. The delete gate remained false and web `/login` GET returned 200.
Read-only provenance check still returned `RECONCILE_PENDING`,
`discovery_reconciled=1`, `jellyfin_reconciled=NULL` for exact operation
`e8b5ba23-cb6d-4e5e-81f6-c1e5fdb79873`.

The production Jellyfin broad inventory GET used the reconciler's configured
`MAX_JELLYFIN_ITEMS=10000` and the requested fields/filters:
`Recursive=true`, `Fields=Path,ParentId`, `IncludeItemTypes=Movie,Video`,
`StartIndex=0`, `Limit=10000`. HTTP 200 returned 364/364 items and exactly one
match for `/media/adult/VEMA/VEMA-246/VEMA-246.mp4`:

- `BROAD_ITEM_ID=0fa5e1cd9743f9e30dc69054e1c12375`
- Path `/media/adult/VEMA/VEMA-246/VEMA-246.mp4`
- ParentId `96243f73185b587bada02c6ee68e760a`
- Type `Movie`, LocationType `FileSystem`, IsFolder `false`
- Name length 141 (full name omitted)
- `BROAD_ID_EQUALS_REMOVED_ID=YES` for removed ID
  `0fa5e1cd9743f9e30dc69054e1c12375`

Using that newly returned BROAD_ITEM_ID, GET `/Items?Ids=...` with API-key
context returned HTTP 200 and count 0. The same exact-ID query with the
previously verified user context returned HTTP 200 and count 0. No user ID or
secret is recorded. The exact title directory remains absent in the Jellyfin
filesystem view. Per the prior PVE forensic evidence supplied for reuse, live
DB is `/opt/jellyfin/config/data/jellyfin.db`, exact DB path row count is 0,
the removal log exists, and the checked post-removal window contains no re-add
evidence. This checkpoint did not reopen the DB or CT112 logs.

Classification meets the specified condition:
`JELLYFIN_PENDING_CLASS=BROAD_INVENTORY_GHOST`. The broad inventory retains an
item-shaped result while exact-ID queries and the database path lookup return
no item. This checkpoint does not change the success invariant, finalize
provenance, or claim the operation committed; that policy decision remains for
the next checkpoint.

Mutation audit: Jellyfin 0, provenance 0, NAS 0, Discovery 0, restart 0.
Only this canonical handoff was updated. Next: decide whether Stage13
Jellyfin success means physical DB row absence or absence from the normal
user-facing tree, then act only in a separate authorized checkpoint.

## 2026-09-29 Stage13-F2M-D6 — API exact-ID / user query forensic (INCOMPLETE)

Initial repo state was expected HEAD `420d0d9e8a3a9526ace2f1fea7257ba477bb81d6`,
branch `teddy-subtitle-stage11`, clean worktree; `origin/teddy-subtitle-stage11`
matched. The existing `ssh pve` route still fails DNS resolution
(`Could not resolve hostname pve`), so no CT112 `pct exec`, Docker console, log,
or DB command ran. No SSH settings changed.

Current invariants were rechecked read-only: the exact NAS title directory is
absent; holding 20 is `present=0`; VEMA-246 present JAV holdings=0; current JAV
holdings=183; exact provenance remains `RECONCILE_PENDING`,
`nas_delete_complete=1`, `discovery_reconciled=1`, `jellyfin_reconciled=NULL`;
delete gate is false; web `/login` GET returned 200.

Production Jellyfin GET-only results:

- API-key `GET /Items?Ids=0fa5e1cd-9743-f9e3-0dc6-9054e1c12375&Fields=Path,ParentId&EnableImages=false&EnableUserData=false`: HTTP 200, `TotalRecordCount=0`, returned items=0.
- User-scoped direct item GET using the already-known valid user context: HTTP 404 (`USER_DIRECT_STATUS=404`). The user ID is intentionally not recorded here.
- User-scoped exact ID query: HTTP 200, `USER_EXACT_QUERY_COUNT=0`.
- General movie/video inventory: HTTP 200, 364/364 items and still one exact path match (`CURRENT_EXACT_PATH_COUNT=1`) at `/media/adult/VEMA/VEMA-246/VEMA-246.mp4`.
- Exact Jellyfin process-side `DirectoryContents` GET for `/media/adult/VEMA/VEMA-246`: HTTP 404. The title directory is absent in the Jellyfin filesystem view; the video cannot exist beneath that missing parent.

The D5/D4 handoff records operator-supplied CT112 evidence that the D2 removal
log exists at `/media/adult/VEMA` and names item
`0fa5e1cd-9743-f9e3-0dc6-9054e1c12375` as removed. D6 could not read bounded
post-removal Docker logs because the PVE route is unavailable:
`READD_AFTER_REMOVE=UNKNOWN`. The API exact-ID queries are both empty, while
the broader path inventory still returns one item. This does not meet the
criteria for API_KEY_ORPHAN_DB_ROW, IN_MEMORY_QUERY_STALE, or another specific
class without runtime DB evidence:
`JELLYFIN_PENDING_CLASS=UNKNOWN`.

The configured host mount `/opt/jellyfin/config -> /config` and the two
approved candidates imply container DB paths `/config/data/jellyfin.db` and
`/config/data/library.db`, but D6 could not inspect their existence from CT112.
Thus `JELLYFIN_DB=UNKNOWN`, `DB_EXACT_ID_ROW_COUNT=UNKNOWN`,
`DB_EXACT_PATH_ROW_COUNT=UNKNOWN`, and parent row/path state=UNKNOWN. No SQLite
connection to an unrelated CT108 path was attempted; no database write or
metadata mutation occurred.

Provenance remains unchanged and pending; no recovery/finalization is
recommended from incomplete evidence. Next checkpoint: use Proxmox web shell
read-only `pct exec 112` access to check only the exact Jellyfin container
paths, the two named DB candidates in SQLite `mode=ro`, parent relation for a
matching row, and Docker logs from 20:00 KST onward filtered to the exact
target. Then decide whether API success requires DB row absence or normal
user-tree absence. Production mutation audit: Jellyfin 0, Jellyfin DB 0, NAS
0, Discovery 0, provenance 0, restart 0. Only this canonical handoff changed.

## 2026-09-29 Stage13-F2M-D5 — item-removal log/API mismatch (INCOMPLETE)

Initial repo state was expected HEAD `503a660aab6c64b71c8cf2fd572d7387069d7554`,
branch `teddy-subtitle-stage11`, clean worktree; remote branch matched. Gate
check remained false, `missav-dlp-web` was Up, `/login` GET returned 200, and
completion timer/service plus reconcile-apply service were inactive. The exact
operation's read-only state still met the pending values: operation
`e8b5ba23-cb6d-4e5e-81f6-c1e5fdb79873`, VEMA-246 / holding 20,
`RECONCILE_PENDING`, `nas_delete_complete=1`, `discovery_reconciled=1`,
`jellyfin_reconciled=NULL`, manifest SHA
`121aefa01eb2d6cd9ae6b99695892cf4652aa4b33d50e65a4c3208b6ef3c8677`, four
removed files / 2,844,317,586 bytes, and `remaining_entries=[]`. Holding 20 is
`present=0`, VEMA-246 present count 0, current JAV holdings 183. All these
database checks were read-only.

The exact-path Jellyfin inventory GET returned HTTP 200, 364/364 items, and
`CURRENT_EXACT_ITEM_COUNT=1` for
`/media/adult/VEMA/VEMA-246/VEMA-246.mp4`, Id
`0fa5e1cd9743f9e30dc69054e1c12375`. Direct `GET /Items/{id}` returned HTTP 400
without a user ID and HTTP 404 when queried with the current user ID. The
exact path inventory still has a matching item despite the direct GET 404.
Therefore no provenance finalization was attempted:
`JELLYFIN_PENDING_CLASS=REMOVE_LOGGED_BUT_API_STILL_PRESENT`,
`JELLYFIN_RECONCILED=NO`, `DELETE_OPERATION_FINAL=NO`,
`CANARY_OPERATION_CLOSED=NO`.

Teddy supplied the following CT112 evidence for this checkpoint: Jellyfin runs
in Docker with read-only mount `/mnt/nas/video/video2/JAV -> /media/adult`; the
exact VEMA-246 title directory and movie are absent; D's direct item refresh
failed with `DirectoryNotFoundException`; D2's parent refresh executed at
`2026-09-29 20:00:12 KST` for `/media/adult/VEMA`; and the Jellyfin log says
Movie item `0fa5e1cd-9743-f9e3-0dc6-9054e1c12375` was removed. These operator
evidence items were not independently re-read in D5. They conflict with the
current API inventory result, so the database must remain pending. No attempt
was made to reconcile the mismatch with another Jellyfin request.

The direct NAS lstat probe did not return a result during this checkpoint; the
known prior exact state is absent. The API mismatch is the active blocker.
Next checkpoint: resolve the GET inventory vs direct item GET/log discrepancy
using GET-only API evidence before selecting any reconciliation step. Do not
send another notification, refresh, scan, or item DELETE. Writer socket
durability remains unproven (`WEB_WRITER_SOCKET_DURABILITY_PROVEN=NO`), so
`STAGE13_CLOSE_READY=NO` even after the canary is eventually closed.

Mutation audit: Jellyfin 0, NAS 0, Discovery 0, provenance 0, service restart
0, mount change 0. Only this canonical handoff was updated.

## 2026-09-29 Stage13-F2M-D4 — CT112 console forensic access blocked (INCOMPLETE)

Initial repo check passed at expected HEAD `7539a2a1cb966b9f2f32beaa4d0f6abf63fc07e8`,
branch `teddy-subtitle-stage11`, clean worktree; `origin/teddy-subtitle-stage11`
matched. The existing `ssh pve` route failed before authentication with
`Could not resolve hostname pve`. Per checkpoint instructions, no alternate
address, SSH setting, or CT112 SSH service was changed or tried.
`PVE_CONSOLE_REQUIRED=YES`. No `pct` command ran and no new CT112 identity,
mount, service, or D/D2 journal evidence was collected.

The prior D3 GET-only evidence remains the latest: Jellyfin 10.11.11; exact
item count 1 at `/media/adult/VEMA/VEMA-246/VEMA-246.mp4`; exact
`/Environment/DirectoryContents` query for `/media/adult/VEMA/VEMA-246`
returned 404; Adult library root `/media/adult`; `LibraryMonitorDelay=60`;
background scan task Idle. D2 had one successful client-side notification
request followed by a 120-second poll with the item still present. Refresher
creation/execution, target, actual CT112 mount source/options, and bounded
server logs remain unknown. Current provenance remains
`RECONCILE_PENDING`, NAS delete complete, Discovery reconciled, Jellyfin flag
NULL. No recovery operation was performed or selected from incomplete evidence.

Next proposed action is **wait-only for production** while Teddy runs the
following read-only bundle in Proxmox web shell (`root@pve`). It prints only
the `mpX` line associated with `/media/adult`; environment output is reduced to
variable names so secrets are not displayed. Then record the results here and
select one recovery action from the evidence.

```sh
# PVE host — status and only the adult media mapping from CT112 config
pct status 112
pct config 112 | awk '/^mp[0-9]+:/ && /\/media\/adult/ {print}'

# PVE host -> CT112 — exact lstat of four paths only
pct exec 112 -- python3 -c 'import os,stat; ps=["/media/adult","/media/adult/VEMA","/media/adult/VEMA/VEMA-246","/media/adult/VEMA/VEMA-246/VEMA-246.mp4"];
for p in ps:
 try:
  s=os.lstat(p); t="symlink" if stat.S_ISLNK(s.st_mode) else "directory" if stat.S_ISDIR(s.st_mode) else "regular_file" if stat.S_ISREG(s.st_mode) else "other"; print(p,"EXISTS",t,"symlink="+str(stat.S_ISLNK(s.st_mode)))
 except FileNotFoundError: print(p,"ABSENT")'

# PVE host -> CT112 — exact mount records
pct exec 112 -- findmnt -T /media/adult -n -o TARGET,SOURCE,FSTYPE,OPTIONS
pct exec 112 -- findmnt -T /media/adult/VEMA -n -o TARGET,SOURCE,FSTYPE,OPTIONS

# PVE host -> CT112 — service identity and version
pct exec 112 -- hostname
pct exec 112 -- systemctl is-active jellyfin
pct exec 112 -- systemctl show jellyfin -p FragmentPath -p User -p Group
pct exec 112 -- sh -lc 'p=$(pgrep -xo jellyfin); test -n "$p" && readlink -f "/proc/$p/exe"'
pct exec 112 -- jellyfin --version

# PVE host -> CT112 — only environment variable names, never values
pct exec 112 -- python3 -c 'import shlex,subprocess; s=subprocess.check_output(["systemctl","show","jellyfin","-p","Environment","--value"],text=True); print("\n".join(sorted({x.partition("=")[0] for x in shlex.split(s) if "=" in x})))'

# If systemd does not own Jellyfin, identify its existing container, then use
# the printed ID in the exact mount/log commands below.
pct exec 112 -- docker ps --format '{{.ID}} {{.Names}} {{.Image}}' | grep -i jellyfin
# PVE host -> CT112 — only /media and /media/adult container mount records
pct exec 112 -- docker inspect --format '{{range .Mounts}}{{if or (eq .Destination "/media") (eq .Destination "/media/adult")}}{{println .Destination .Source .Type .RW}}{{end}}{{end}}' <JELLYFIN_CONTAINER_ID>
pct exec 112 -- docker exec <JELLYFIN_CONTAINER_ID> jellyfin --version
pct exec 112 -- docker exec <JELLYFIN_CONTAINER_ID> python3 -c 'import os,stat; ps=["/media/adult","/media/adult/VEMA","/media/adult/VEMA/VEMA-246","/media/adult/VEMA/VEMA-246/VEMA-246.mp4"];
for p in ps:
 try:
  s=os.lstat(p); t="symlink" if stat.S_ISLNK(s.st_mode) else "directory" if stat.S_ISDIR(s.st_mode) else "regular_file" if stat.S_ISREG(s.st_mode) else "other"; print(p,"EXISTS",t,"symlink="+str(stat.S_ISLNK(s.st_mode)))
 except FileNotFoundError: print(p,"ABSENT")'

# PVE host -> CT112 — D window; bounded to the incident timestamps
pct exec 112 -- sh -lc 'journalctl -u jellyfin --since "2026-09-29 18:00:00 KST" --until "2026-09-29 18:16:30 KST" --no-pager -o short-iso | grep -Ei "VEMA-246|/media/adult/VEMA|FileRefresher|will be refreshed|ReportFileSystemChanged|Error processing directory changes|Error finding the item affected|Error refreshing|LibraryMonitor" | sed -E "s/((api.?key|token)[=: ]+)[^ ]+/\\1[REDACTED]/Ig"'

# PVE host -> CT112 — D2 window; bounded to the incident timestamps
pct exec 112 -- sh -lc 'journalctl -u jellyfin --since "2026-09-29 19:50:00 KST" --until "2026-09-29 20:06:30 KST" --no-pager -o short-iso | grep -Ei "VEMA-246|/media/adult/VEMA|FileRefresher|will be refreshed|ReportFileSystemChanged|Error processing directory changes|Error finding the item affected|Error refreshing|LibraryMonitor" | sed -E "s/((api.?key|token)[=: ]+)[^ ]+/\\1[REDACTED]/Ig"'

# For a Jellyfin container instead of systemd, run each bounded log query
# against its existing ID (PVE host; the range remains bounded at docker logs).
pct exec 112 -- docker logs --since '2026-09-29T18:00:00+09:00' --until '2026-09-29T18:16:30+09:00' <JELLYFIN_CONTAINER_ID> 2>&1 | grep -Ei 'VEMA-246|/media/adult/VEMA|FileRefresher|will be refreshed|ReportFileSystemChanged|Error processing directory changes|Error finding the item affected|Error refreshing|LibraryMonitor' | sed -E 's/((api.?key|token)[=: ]+)[^ ]+/\1[REDACTED]/Ig'
pct exec 112 -- docker logs --since '2026-09-29T19:50:00+09:00' --until '2026-09-29T20:06:30+09:00' <JELLYFIN_CONTAINER_ID> 2>&1 | grep -Ei 'VEMA-246|/media/adult/VEMA|FileRefresher|will be refreshed|ReportFileSystemChanged|Error processing directory changes|Error finding the item affected|Error refreshing|LibraryMonitor' | sed -E 's/((api.?key|token)[=: ]+)[^ ]+/\1[REDACTED]/Ig'
```

Do not run the bounded journal commands if Jellyfin is a container rather than
a systemd service; first identify its existing container and inspect only that
container's exact `/media/adult` mount. Do not start services, attach disks,
refresh libraries, or alter mounts as part of this access checkpoint.

## 2026-09-29 Stage13-F2M-D3 — exact Jellyfin stale-item forensic (INCOMPLETE)

This checkpoint was read-only apart from this handoff. Initial repository state
was clean at expected HEAD `fc7ebec68e0700da4f18a62e747af2a2bc9ddcaf`, branch
`teddy-subtitle-stage11`; `git ls-remote origin refs/heads/teddy-subtitle-stage11`
matched that exact commit. This checkout has no stored remote-tracking ref or
upstream config for the branch, so `@{u}` itself is unavailable.

The exact operation `e8b5ba23-cb6d-4e5e-81f6-c1e5fdb79873` still matches the
known state on CT108: provenance is `RECONCILE_PENDING`,
`nas_delete_complete=1`, `discovery_reconciled=1`, `jellyfin_reconciled=NULL`;
holding 20 is `present=0`, zero VEMA-246 JAV holdings are present, and current
JAV holdings are 183. The provenance and Discovery SQLite reads used
`mode=ro`. The current exact NAS lstat could not be completed: the configured
SSH probe from the web container exited before returning a path result. The
prior confirmed NAS state remains absent, but this checkpoint cannot attest a
fresh NAS probe.

Production Jellyfin GET `/System/Info` returned:

- `Version=10.11.11`
- `ProductName=Jellyfin Server`
- `OperatingSystem=""` and `Architecture=null` as exposed by this endpoint
- `ServerName=Jellyfin-Sernver`

The exact movie inventory query (`Recursive=true`, `Fields=Path`,
`IncludeItemTypes=Movie,Video`, `StartIndex=0`, `Limit=50000`) returned 364 of
364 items and one exact path match:

- Id `0fa5e1cd9743f9e30dc69054e1c12375`
- Name `My wife, the CEO's secretary, who works at the same company as me, was getting creampied in the CEO's office while I was at work. Ruu Totsuka`
- Path `/media/adult/VEMA/VEMA-246/VEMA-246.mp4`
- Type `Movie`, MediaType `Video`, LocationType `FileSystem`, IsFolder `false`
- ParentId was null in the inventory DTO; DateCreated/DateLastSaved were not
  exposed in that query

Direct GET `/Items/{id}` returned HTTP 400 without UserId and HTTP 404 with the
only user ID returned by `/Users`; `/Items/{id}/Ancestors` also returned 404.
Therefore the exact item identity is visible in the inventory, but direct item
lookup and its ancestor chain (title folder, VEMA, Adult/JAV root) remain
unverified. No item ID or ancestor path was inferred from a failed direct GET.

GET `/Library/VirtualFolders` returned Adult with `Locations=["/media/adult"]`,
`ItemId=0a7fd8175719d8f7ebfb93874e55a2d5`, and `EnableRealtimeMonitor=null`
(not exposed). The Movie library maps to `/media/movie`. The Adult virtual
folder agrees with the item's `/media/adult` prefix; no mapping mismatch is
indicated by API configuration. CT112's actual mount mapping was not verified.
SSH to `root@192.168.1.205` was denied by public-key authentication. A bounded
GET to Jellyfin's `/Environment/DirectoryContents` for only the exact title
directory `/media/adult/VEMA/VEMA-246` returned HTTP 404. The Jellyfin process
therefore reports the exact title directory absent, and the movie file cannot
be visible below that absent directory:
`JELLYFIN_FS_TITLE_DIR_VISIBLE=NO`, `JELLYFIN_FS_FILE_VISIBLE=NO`.
Given the known NAS-absent state, `MOUNT_VIEW_STALE=NO`. CT112's family/root
lstat details, filesystem type/source/options/read-only status, and mount
identity remain UNKNOWN because SSH was denied; the exact title-directory API
check does not establish them. No recursive scan, broad listing, or `du` was
run.

GET `/System/Configuration` returned `LibraryMonitorDelay=60` seconds.
GET `/ScheduledTasks` showed “미디어 라이브러리 스캔” (`RefreshLibrary`) as
`Idle`; its last execution completed at `2026-09-29T06:46:36.5822535Z`
(`15:46:36 KST`), before the D2 window. No current long-running scan is
evidenced by that task API response.

The D and D2 Jellyfin log checks are incomplete. The D2 report from the prior
checkpoint records one `/Library/Media/Updated` POST followed by its full
120-second poll, and the item remained. That control flow means the client
did not record a request exception, so `D2_EVENT_ACCEPTED=YES` at the client
level; the HTTP status was not preserved. The current web container started at
`2026-09-29T10:58:27Z` with restart count 0, and its bounded D (17:55–18:20 KST)
and D2 (19:55–20:30 KST) docker-log windows contain no matching item/Jellyfin
lines. CT112 journal/container logs were not available because SSH was denied.
Thus `D2_REFRESHER_CREATED=UNKNOWN`, `D2_REFRESHER_EXECUTED=UNKNOWN`, and
`REFRESH_TARGET_PATH=UNKNOWN`; no production target is inferred.

The production-version source tag `v10.11.11` was checked read-only. Its
`LibraryController.PostUpdatedMedia` passes each DTO item's Path to
`ReportFileSystemChanged` and does not branch on UpdateType; `FileRefresher`
waits `LibraryMonitorDelay`, then walks toward a library item and up through
owner/parent items while the item's path does not exist. It calls
`ChangedExternally()` on the resolved item. This confirms that `Deleted` is not
a direct delete command. It does not establish which target was reached in
production. Source references:
`https://github.com/jellyfin/jellyfin/blob/v10.11.11/Jellyfin.Api/Controllers/LibraryController.cs`
and
`https://github.com/jellyfin/jellyfin/blob/v10.11.11/Emby.Server.Implementations/IO/FileRefresher.cs`.

Current exact path count is 1 (`CURRENT_EXACT_ITEM_COUNT=1`); the item did not
disappear in this checkpoint. Classification is
`JELLYFIN_PENDING_CLASS=UNKNOWN`: exact title dir/file are absent from the
Jellyfin API filesystem view and the API root mapping agrees, but the CT112
mount identity and server refresher logs are unavailable. The available
evidence rules out a visible stale title mount, but cannot distinguish an
unprocessed event from a completed parent refresh that left the item record.
No single production recovery action is selected until the bounded D/D2 logs
show whether the expected parent refresh executed. Next checkpoint: obtain
read-only CT112 access, inspect only the exact file/family/root paths and
`/media/adult` mount record, then read only the D/D2 journal windows and choose
one recovery action. Do not send another notification or refresh before that
classification.

Mutation counts for this checkpoint: source code 0, Jellyfin 0, NAS 0,
Discovery 0, provenance 0, runtime restart 0. Delete gate remains false.
Writer socket durability remains unproven; its known state remains host READY,
web visible/connectable, durability unproven.

## 2026-09-29 Stage13-F2H pinned completion runtime — FAIL / review required

The F2G blocker was addressed for the scheduled completion/organizer path. An
immutable release was installed at
`/opt/missav-dlp-web/stage9-runtime/releases/26c8657d4bd5c5b767f2f8eb474a80ff9121a150/`
from exact commit `26c8657d4bd5c5b767f2f8eb474a80ff9121a150`. It contains the
24-module local import closure of the completion runner, including
`teddy_title_exclusion.py`, the completion orchestrator, organizer apply,
operation lock, and DVD-ID parser. Release files are read-only; source SHA-256
was checked against `git show` for each archived file. Core hashes:
title exclusion `a4dd0d847cb05a20146f69f62d08ae29e626e997a49c203c1ad70d688b28e1ab`,
completion orchestrator `41cf203b552b246f8095b8025bf281d8633f9e2d893bf886fe430de7c53b38d0`,
organizer apply `559602f0e36f179df243072c5916ddf1009f1d2517ae83207807ae049cf3b93d`.

`/usr/local/sbin/teddy-completion-stage9-runner` was atomically switched to the
version-pinned release. It checks the release marker, sets
`TEDDY_TITLE_LOCK_DIR=/opt/missav-dlp-web/title-locks`, pins `PYTHONPATH` to
that release, and uses `/usr/bin/python3` (3.13.5) as root:root. The previous
wrapper is preserved at
`/opt/missav-dlp-web/backups/stage13-f2h-20260929-1225-teddy-completion-stage9-runner`;
the old `42339ea7...` runtime remains untouched. Release imports and the
completion orchestrator, organizer apply, runner, and process-flock fixture
smokes passed offline. Source order is per-title lock before the existing
global completion operation lock.

Host runtime ↔ web cross-process checks passed in both directions:
same-title contention returned `BUSY`, the host and container observed the
same lock inode, holder termination released the lock, and a second canonical
DVD-ID remained independently acquirable. The production web remains on the
F2F image, delete gate is false, writer health is `READY`, and Discovery DB
mount is read-only.

Stage12 has no systemd/cron automatic launcher. Its documented manual command
uses the checked-out F2F source and requires
`TEDDY_TITLE_LOCK_DIR=/opt/missav-dlp-web/title-locks`; no Stage12 run occurred.
The separate manual `teddy-discovery-jav-reconcile-apply.service` still points
at the old Stage9 runtime and was not invoked; review its role/lock boundary
before claiming broader Discovery-writer exclusion.

**A timer side effect prevents a clean PASS.** During timer restoration,
`systemctl start teddy-completion-stage9.timer` immediately triggered the
scheduled service due to its overdue `OnUnitInactiveSec`. Its result had
`total=0`, `eligible=0`, `applied=0`, and media reconciliation created 0 jobs;
however, it retried one existing media job, which failed and updated that
media-state row (`attempt_count=17161`). The stored error was not exposed. The
failure point relative to NAS metadata publication and Jellyfin notification
cannot be established from the safe result, so those side effects are
**UNKNOWN**, not asserted zero. Present holdings remained 184, organizer
active jobs 0, Stage12 active rows 0, writer health remained ready, and no
delete/provenance operation occurred. The completion timer is currently
inactive (still enabled) to prevent another retry pending review. The F2H
launcher/runtime was not rolled back; its lock checks passed. Before resuming
the timer, inspect the failed media job and decide how to handle its retry.

## 2026-09-29 Stage13-F2G shared title-lock production deployment — INCOMPLETE

The exact F2F web source `26c8657d4bd5c5b767f2f8eb474a80ff9121a150` is
deployed as image `sha256:bac75af6716cd7a0e33aa671b90f9386926d8dc93f64dba201caa6494283e404`
(`missav-dlp-web:stage13f2g-26c8657`). The previous running image
`sha256:40d68b117add00b0dfa85748780d49c3578e670af42d11aa2ae9dfda805dc787`
was retained locally as `missav-dlp-web:rollback-f2g`. Only
`missav-dlp-web` was recreated. It is running with restart count 0; `/login`
and static Library assets return 200, `/` redirects unauthenticated users,
and unauthenticated Library and delete-prepare API requests return 401.

Production Compose/env now persist the host lock root
`/opt/missav-dlp-web/title-locks` at container path `/run/teddy-title-locks`,
with `TEDDY_TITLE_LOCK_DIR=/run/teddy-title-locks` in the web container.
The host directory is root:root mode 0750; lock files are regular files mode
0600. Host completion/systemd, the documented host Stage12 runner, and the web
container currently execute as UID/GID 0; the web container additionally has
GID 988. The host and container saw the same lock device/inode for the
`ADN-785` connectivity probe. Host-held to container and container-held to
host contention both returned `BUSY`; killing the container-side holder
released the kernel lock; a different canonical DVD-ID remained acquirable
while `ADN-785` was held. These were lock-only probes; empty lock files are
left in place by design.

The web feature gate is explicitly `TEDDY_LIBRARY_DELETE_ENABLED=false`.
The Discovery database remains mounted read-only and the writer socket remains
read-only. Writer health is `READY` on host and container. Exact
`ADN-785` `preflight_holding` returned `READY` using a rollback-only
`BEGIN IMMEDIATE`; `present=1`, holding identity, and the current holding count
were unchanged.

Current read-only snapshot: 184 present JAV holdings, 184 unique DVD-IDs, no
duplicates, and no canonical/parse mismatches. Organizer active jobs: 0;
Stage12 `RUNNING`/`GENERATED`: 0; heartbeat: stale `COMPLETE` with no active
title inference.

**Canary remains blocked.** The active production completion wrapper
`/usr/local/sbin/teddy-completion-stage9-runner` pins
`/opt/missav-dlp-web/stage9-runtime` at commit
`42339ea7fb01f62f798baa04d5e774f644b7f46f`; its completion orchestrator and
organizer apply module differ from the F2F integrated source and do not use
the per-title lock. The reconcile apply launcher also points at that old
runtime. Their configured execution UID is root, but setting the lock env
alone cannot provide exclusion while this old source remains active. No host
runner or writer service was run or restarted for this checkpoint.

Stage12 has no persistent systemd service; its documented manual runner uses
the checked-out F2F-integrated module. Any future invocation must explicitly
set `TEDDY_TITLE_LOCK_DIR=/opt/missav-dlp-web/title-locks` in that command's
environment. Do not treat current idle counts as a substitute for this lock.
The next checkpoint must install/activate an exact, version-pinned F2F
completion/organizer runtime and persistent lock-root configuration, then
repeat cross-runtime exclusion. Until that is done:
`SHARED_PER_TITLE_LOCK=NO` for production participants and
`CANARY_READY=NO`. Delete gate stays false; actual delete, Discovery content
write, provenance write, NAS write, Jellyfin refresh, and subtitle generation
remain 0.

## 2026-09-29 Stage13-F2F shared per-title exclusion — PASS (offline/source)

The F2E remaining `SHARED_PER_TITLE_LOCK_UNAVAILABLE` race boundary is closed
for the current organizer/completion, Stage12 batch, and Library delete paths.
They now share `teddy_title_exclusion.try_acquire_title_lock()` and a
non-blocking `fcntl.flock(LOCK_EX | LOCK_NB)` keyed by canonical DVD-ID.

Execution paths are on CT108 `downloader` (the same host namespace documented
in the Stage12 runtime contract). The canonical deployment binds host
`/opt/missav-dlp-web/title-locks` to the web container at
`/run/teddy-title-locks`; host runners use the host path and the web app uses
the container path, which refer to the same bind-backed directory/inodes.
`TEDDY_TITLE_LOCK_DIR` is required by all callers; missing/unsafe lock roots
fail closed. Lock files contain no payload. Future automatic subtitle runners
MUST acquire this same per-title lock.

Lock order is per-title lock before the existing organizer apply lock or
completion `operation_lock`. Stage12's singleton runner lock remains outside
the per-title scope; it does not participate in the opposing delete/completion
lock order. The Stage12 rollout writer lock is acquired only briefly inside
the per-title lock. No StateStore-writer-to-title-lock path was found.

- Organizer apply holds the title lock from before its existing apply lock
  through publish, holding/job updates, source cleanup, and terminal job state.
- Completion `process_one` takes title lock, then `operation_lock`, and holds
  both through canonical publish, holding/job update, and cleanup.
- Stage12 obtains the title lock before durable RUNNING and holds it through
  controller work, publication, Jellyfin recognition, and terminal rollout
  transition. BUSY returns `HELD_TITLE_BUSY` without changing durable state.
- Delete commit and partial mutation resume acquire the same lock after the
  first activity check and Discovery writer preflight. While held they repeat
  activity and identity/manifest validation, then retain the lock through NAS
  mutation, Discovery/Jellyfin reconciliation, provenance finalization, and
  token finalization. Reconcile-only recovery remains available without the
  lock. Busy returns `delete_target_busy`; unavailable lock infrastructure
  returns `delete_exclusion_unavailable`, both before mutation.
- The F2E durable activity guard remains in place as a state sanity check;
  shared flock supplies cross-process exclusion.

Separate-process flock fixtures prove same-title BUSY, different-title
parallelism, release after normal exit, and kernel lock release after process
termination while the empty lock file remains. Organizer, Stage12, and delete
fixtures verify their lock scope and no-work-on-BUSY behavior. Regression
smokes and the full Docker image build passed.

`SHARED_PER_TITLE_LOCK=AVAILABLE` and `TOCTOU_CLOSED=YES` for these integrated
source paths when the canonical host-backed mount/env is deployed. This is
source/fixture evidence only; production deployment has not occurred. Feature
gate remains false, production deploy/restart = NO, actual delete = 0. Stage13
F2G must deploy the shared lock mount/env and verify runtime wiring before any
canary readiness decision.

## 2026-09-29 Stage13-E2D origin forensic — PASS

The exact production rejection for the authenticated ADN-785 delete DRY-RUN
prepare was confirmed:

- response code: `invalid_request_origin`
- guard subreason: `scheme_mismatch`
- browser Origin: `https://downloader.ssikgun.com`
- Flask request view: scheme `http`, host `downloader.ssikgun.com`
- `X-Forwarded-Proto=https`
- `X-Forwarded-Host`: missing
- `Sec-Fetch-Site=same-origin`

Therefore the failure is specifically reverse-proxy/public-origin scheme
normalization. The public host itself matches; the request reaches Flask as
HTTP while the browser correctly identifies the public origin as HTTPS.

No ProxyFix or other app-wide trusted forwarded-header normalization primitive
currently exists. The upstream proxy/trust-hop topology is not sufficiently
documented to justify blindly trusting arbitrary forwarded headers.

Frozen fix direction:

- keep authentication, JSON/intent, Origin, host, and same-site checks;
- do not weaken or remove Origin validation;
- do not trust arbitrary `X-Forwarded-*` headers;
- add a centrally configured trusted public origin (for example
  `TEDDY_PUBLIC_ORIGIN`) and an app-wide helper that parses/canonicalizes that
  configured origin;
- compare browser Origin against that configured trusted public origin and keep
  request-host validation consistent with the configured public host;
- do not hard-code `downloader.ssikgun.com` inside production logic;
- fail closed if the configured public origin is absent or invalid for this
  destructive-intent path.

Safety state remains:

- token issued: NO
- validate reached: NO
- delete/commit endpoint: absent
- NAS/DB/Jellyfin write/delete: 0

Next checkpoint is implementation + fixture validation of the configured
public-origin helper. Production deployment remains a separate checkpoint.


## 2026-09-29 Stage13-E2C manual reproduction — invalid_request_origin confirmed

Teddy manually retried the authenticated production DRY-RUN prepare for
`ADN-785` after the diagnostics-only deployment.

Observed UI-safe error code:

`invalid_request_origin`

This confirms the request passes authentication and the JSON/intent boundary,
then fails inside the origin/same-site portion of the delete-intent guard.

The exact origin subreason is still pending app-log inspection. It must be read
from the bounded diagnostics added in Stage13-E2C and classified as one of the
known safe branches such as `origin_missing`, `scheme_mismatch`,
`host_mismatch`, or `cross_site`.

Safety state remains unchanged:

- token issued: NO
- validate reached: NO
- delete/commit endpoint: absent
- NAS/DB/Jellyfin write/delete: 0

Do not change or relax the guard until the exact logged subreason and sanitized
request/origin/forwarded-header relation are confirmed.


## 2026-09-29 FNS-247 external subtitle parser/alignment replay — PARTIAL

Generic source changes completed in Stage11 subtitle parsing and alignment:

- SRT parsing may drop at most one structurally valid zero-duration cue per
  document. Cue index/text are validated, the original payload hash and byte
  size remain bound to the parsed document, and all other timestamp/content
  validation remains strict. Dropped source indexes are exposed as immutable
  `SubtitleDocument.dropped_cue_indexes` metadata.
- Alignment comparison text replaces only CR/LF with spaces in its derived
  value. Stored cue text and timing remain unchanged; other control characters
  still fail validation.
- No title-specific parser, cue, acceptance, or production path was added.

Offline checks:

- `teddy_discovery_subtitle_text_smoke.py`: PASS, including one-drop admission
  and rejection when more than one zero-duration cue is present.
- `teddy_discovery_alignment_smoke.py`: PASS, including multiline cue text
  preservation, CR/LF comparison normalization, and rejection of tab controls.
- `teddy_discovery_alignment_acceptance_smoke.py`: PASS; frozen acceptance
  gates are unchanged.
- `teddy_discovery_stage11_live_adapters_smoke.py`: not run to completion;
  this environment lacks the `numpy` dependency (`ModuleNotFoundError`).

Exact supplied-input read-only replay:

- JA source: `/var/tmp/FNS-247.user-external-ja.srt`, SHA-256
  `8e645dd1e55304075b03562ae38837012d401a6cb00cb96fc8d54d9df2508598`.
- Baseline ASR was read from the existing stage12 artifact and reconstructed
  in memory; no NAS, Jellyfin, rollout DB, or current KO file was written.
- Parser admitted 313 cues and recorded one dropped cue, original SRT index
  153. All 313 cues reached lexical candidate generation (233 candidates at
  the unchanged 0.80 score floor).
- Alignment did not produce an affine result: strict monotonic selection
  raised `AlignmentAmbiguityError` for equal-strength chains. The same guard
  also fired when candidate score floors were raised to 0.90, 0.95, and 1.00.
  No selector or acceptance threshold was bypassed or weakened.
- Acceptance verdict: **UNRESOLVED / no ACCEPT_HYBRID or REJECT_EXTERNAL
  decision emitted**. Anchor/inlier counts and ratio are not available because
  affine alignment was not inferred. A future checkpoint may address generic
  repeated-text anchor ambiguity; until then, the production external-JA path
  remains fail-closed for this replay.

Source changes and this handoff are committed as `54010d7` and pushed to
`origin/teddy-subtitle-stage11`.

## 2026-09-29 Stage13-E2B prepare-guard forensic — INCOMPLETE

Production manual delete-prepare attempts for `ADN-785` returned HTTP 403
three times. Authentication had already succeeded; therefore the request was
rejected inside the Library delete-intent guard before manifest inspection or
token issuance.

Confirmed safety state:

- prepare HTTP status: 403
- exact branch between `invalid_request_boundary` and
  `invalid_request_origin`: not yet observable from current logs/UI
- token issued: NO
- validate reached: NO
- NAS/DB/Jellyfin write/delete: 0
- production restart/source change during forensic: 0

Current access logs do not record response JSON or the sanitized request/proxy
metadata needed to distinguish the two guard branches. The UI currently turns
all non-success prepare responses into the same generic message.

Next checkpoint is a diagnostics-only hotfix:
1. keep all existing delete-intent checks unchanged;
2. add bounded structured logging for the rejected guard branch and sanitized
   origin/host/forwarded-header metadata;
3. allow the UI to display only an allowlisted safe error code for
   delete-prepare/validate failures;
4. redeploy only the web app and reproduce once.

Do not weaken Origin checking, trust arbitrary forwarded headers, or enable any
delete/commit endpoint.


## 2026-09-28 Stage13-E2 manual prepare attempt — FAIL / forensic required

Teddy manually opened the production File Management delete DRY-RUN for
`ADN-785` from an authenticated browser session. The dialog opened, but the
prepare request did not return a usable PREPARED payload and the UI showed:

`삭제 준비 정보를 확인하지 못했습니다.`

Important safety facts:

- No validate request was reached.
- No delete/commit endpoint exists.
- No NAS/DB/Jellyfin write was performed by this manual attempt.
- The previously bounded internal manifest for ADN-785 was readable, so the
  failure must be narrowed at the production HTTP prepare boundary before any
  source change.

Potential but **unconfirmed** suspect: the prepare guard compares browser
`Origin` against Flask `request.host_url`. Behind the production reverse
proxy, scheme/host normalization may differ (for example external HTTPS versus
internal HTTP) even for a legitimate same-origin browser request. Do not change
this guard until the actual response status/error code and proxy header view are
captured.

Next checkpoint is read-only forensic of the exact production prepare request:
HTTP status, safe JSON error code, relevant app/access log evidence, and
sanitized request/proxy origin-host metadata. Actual deletion remains disabled.


## 2026-09-28 Stage13-E2A current-holdings delta forensic — PASS

The previous Stage13-A/C value of 177 present JAV holdings was a point-in-time
snapshot, not a permanent production invariant.

Current read-only Discovery state:

- present JAV holdings: **184**
- unique DVD-ID: **184**
- MATCHED: **184**
- duplicate DVD-ID: **0**
- canonical/parse mismatch: **0**

Seven holdings have `first_seen_at` after the prior 177 snapshot boundary and
all seven are classified as `NEW_CANONICAL_HOLDING_CONFIRMED`:

- EROFV-313
- SVVRT-086
- NTR-102
- DAL-012
- FTHT-361
- FTHTD-219
- FTHTD-228

Each has `discovered_by=completion-stage9` and one matching COMPLETED organizer
job for the same canonical destination. This confirms the current 184 count is
explained by verified new canonical holdings since the prior snapshot. The
organizer timestamps are completion evidence, not exact filesystem placement
instants.

Historical removal reconstruction remains unavailable because the current
schema does not preserve a complete holding-transition history. Do not infer
that no historical removal ever occurred.

Current Stage12 relationship:

- Stage12 rollout rows remain **173**.
- Current holdings without a Stage12 rollout row: **11**
  (`DAL-012`, `EBWH-296`, `EROFV-313`, `FTHT-361`, `FTHTD-219`,
  `FTHTD-228`, `MIAD-866`, `MIRD-258`, `NTR-102`, `SKMJ-774`,
  `SVVRT-086`).

Frozen Stage13 contract:

- File Management `total_titles` is derived from the **current** read-only
  `storage_root='jav' AND present=1` holdings snapshot at request time.
- Never use 177 (or any other historical count) as a production hard gate.
- Stage12 terminal state remains an optional LEFT JOIN.
- Current holdings without Stage12 rollout rows are valid File Management items.
- Stage13-E2 prepare/validate canaries must compare against the current snapshot
  captured immediately before the canary.

The remaining E2 blocker is only the authenticated same-origin
prepare/validate/replay canary. Actual delete remains disabled.


## 2026-09-28 Post-Stage13 subtitle automation — progress visibility requirement

When the post-Stage13 automatic subtitle workflow for newly completed downloads
is implemented, File Management > `자막 처리 현황` must become the operational
progress view for that automation.

Required visible progress semantics:

- Always show the currently processing DVD-ID when a subtitle job is active.
- Show the current pipeline stage with a short human-readable Korean label
  (for example inventory check, ASR, evidence preparation, Hermes semantic
  translation/review, publication, Jellyfin verification).
- When Hermes is processing split semantic parts, show exact progress as
  `Part n/N`, using the existing controller/runtime progress source rather
  than guessing from elapsed time.
- Preserve the current status summary counts and heartbeat/last-activity
  information, but distinguish active-job progress from aggregate library
  holdings counts.
- Idle state must clearly say there is no current title.
- Retry/failure/unresolved states must remain title-local and expose a concise
  machine-derived reason without subtitle body/raw response/session identity.
- The UI should update from the durable job/controller state so browser reloads
  do not lose the current progress view.
- This requirement belongs to the post-Stage13 new-download subtitle automation
  work; do not expand Stage13 permanent-delete scope to implement it now.


## 2026-09-28 Stage13-C visual acceptance — CLOSED / PASS

Manual authenticated browser verification by Teddy confirmed the final Stage13-C
File Management UI in dark mode.

Accepted visual state:

- Sidebar exposes a single `파일 관리` destination for durable JAV holdings.
- File Management contains `보유 라이브러리` and `자막 처리 현황` subtabs.
- Subtitle processing status is no longer shown in Settings.
- The subtitle status panel, metric cards, badge, labels, and footer now honor
  the application dark theme and remain readable.
- The visible production status panel showed idle state, current title none,
  `PUBLISHED=163`, `PENDING=0`, `FAILED_RETRYABLE=0`,
  `FAILED_TERMINAL=0`, and `UNRESOLVED=10`; its heartbeat was shown as
  stale/old, matching the read-only status source rather than being hidden.
- The manual screenshot showed no catastrophic horizontal overflow or theme
  breakage in the accepted desktop view.

Stage13-C is therefore **CLOSED / PASS**.

The current production web candidate is the Stage13-C6 image built from source
HEAD `b63bd132bc75753b8b1127cb792e42c4b33e8324`
(image prefix previously recorded as `sha256:7f427ebf...`). No rollback is
required.

Next Stage13 work must continue from the frozen permanent-delete plan. Do not
reopen Stage13-C unless a concrete regression is found.


## 2026-09-28 Stage13-C4 manual visual finding — dark-theme defect

Manual authenticated visual inspection confirmed the Stage13-C3/C4 navigation
refactor is present in production, but **Stage13-C remains open** because the
`자막 처리 현황` panel does not honor the application's dark theme.

Observed defect:

- The surrounding File Management page is correctly dark.
- `templates/teddy-subtitle-status.css` still hard-codes light panel,
  metric-card, border, and text colors.
- Unlike the Stage13 Library CSS, it has no
  `html[data-theme="dark"]` overrides.
- The result is a large light status card inside an otherwise dark page.

Required next fix is UI-only:

- add scoped dark-theme overrides for the subtitle-status panel, metric cards,
  text, border, and status badges while preserving meaning-first labels;
- keep light theme unchanged;
- do not change subtitle status API/polling/state semantics;
- validate both light and dark rendering and narrow layout;
- redeploy only the web app and keep DB/NAS/Jellyfin writes at zero.

The production Stage13-C4 candidate remains running until this visual defect is
fixed and manually accepted.


## 2026-09-28 Stage13-C UI information-architecture correction

User clarified the original Files page is **not** the durable JAV library. It
shows downloader-side files only while they remain in the downloader storage;
after the organizer moves a completed title into the canonical JAV library,
that title disappears from the old Files page. This disappearance is the
reason Stage13 exists.

Freeze the UI semantics accordingly:

- The new Stage13 current-holdings Library view is the durable **File
  Management** destination and should become the single sidebar
  `파일 관리` entry.
- Do not keep a second sidebar entry that competes with it as
  `영상 라이브러리`.
- The legacy Files view is transient/downloader-side state, not the permanent
  library. Preserve its functionality, but relocate/rename it under the
  Download area as a secondary view such as `다운로드 파일` / `정리 전 파일`;
  it must not be presented as the primary File Management destination.
- Move the existing `자막 처리 현황` panel out of Settings into the durable
  File Management area. It is operational/library status, not a preference.
- File Management should therefore center on:
  1. current JAV holdings/library (default),
  2. subtitle processing status/monitoring.
- Settings should retain actual configuration/system controls only.
- Existing transient Files playback behavior must remain available after the
  navigation move; no functionality should be silently removed.
- Permanent-delete work later in Stage13 belongs to the durable JAV File
  Management view, never the transient downloader Files view.

This is a Stage13-C information-architecture correction before formal C
closure; production candidate remains deployed pending this UI refinement and
manual visual acceptance.


## 2026-09-28 Stage13-A forensic / contract freeze — PASS

Stage13-A read-only forensic is complete. No source, DB, NAS, Jellyfin, Hermes,
or VM122 production write occurred during the forensic.

### Repository identity

- Branch: `teddy-subtitle-stage11`
- Stage13-A final local HEAD after handoff-only fast-forward:
  `9d6b8b8b590122051ca7c763cb9c7d0e88456795`
- Worktree was clean.
- The prior apparent remote mismatch was caused by a stale
  `origin/teddy-subtitle-stage11` tracking ref; the branch is not present in the
  configured `remote.origin.fetch` refspec. Exact `ls-remote` confirmed the
  server branch at the expected handoff-only commit.

### Stage13-B frozen read-model contract

- File Manager source set is current Discovery holdings, not Stage12 rollout.
- Current present JAV holdings: **177**.
- Stage12 rollout rows: **173**.
- File Manager joins current holdings with Stage12 terminal state using an
  optional/LEFT JOIN boundary. A holding without a Stage12 row must still be
  visible and manageable.
- The four present holdings without a Stage12 rollout row are:
  `EBWH-296`, `MIAD-866`, `MIRD-258`, and `SKMJ-774`. All currently record
  `discovered_by=completion-stage9`. Do not claim they were downloaded after
  Stage12 closure without separate evidence.

### NAS addition-date contract

Read-only bounded sampling used canonical DB paths only. Six sampled titles
(two each from `library-inventory`, `organizer-apply`, and
`completion-stage9`) were checked through the dedicated NAS SSH boundary.
The NAS filesystem was Btrfs. Filesystem birth/creation time was unavailable
for both title directories and media files; directory ctime was not reliable
as final-placement time, and media mtime is not accepted by itself as download
or placement time.

Every one of the 177 current holdings has a matching COMPLETED organizer job
for its exact canonical destination. For 176 titles, publisher job creation
and completion fall on the same KST calendar date, which bounds final placement
to that date and is sufficient for the Stage13 UI date display. One title
crosses a KST date boundary, so its historical `nas_added_at` remains null and
its UI must show `추가 날짜 확인 불가`. Do not invent an approximate date.

For future newly completed titles, record the successful final JAV publication
instant as durable `nas_added_at` provenance so this ambiguity does not recur.

### NAS / mount boundary

In the current CT108 shell namespace, `/mnt/nas-jav` and
`/mnt/nas-downloads` are ordinary paths on the local ext4 root filesystem,
not the JAV NAS mount; `/final` is absent. Therefore:

- `JAV_LOCAL_MOUNT=NOT_PRESENT_IN_CURRENT_NAMESPACE`
- Stage13 metadata/size reads use exact bounded NAS SSH operations.
- Browser playback uses validated canonical title identity through a minimal
  adapter over the existing player/stream behavior.
- Future permanent delete uses a dedicated NAS SSH mutator.
- Do not make the CT108 JAV mount writable or depend on a local RW JAV mount.

### Next checkpoint

Proceed to **Stage13-B — read-only backend / read model**. Implement list/detail,
server-side search, filters, sorting, bounded per-title/library size accounting,
KO / UNRESOLVED / Jellyfin state, NAS addition-date display contract, and the
minimal browser-playback adapter. Do not implement permanent delete yet.


## 2026-09-28 Post-Stage13 next priority — automatic subtitles for newly completed downloads

This requirement is intentionally **outside Stage13** so the Stage13 NAS Library
File Manager can be completed without changing the subtitle production
pipeline.

After Stage13 is CLOSED / PASS, the next priority is to automate subtitle
follow-up for **newly downloaded/completed titles**. Stage12 closed the bounded
rollout for the already-held library; it must not be treated as an ongoing
whole-library job.

Required future behavior:

- Trigger only after a newly downloaded title has completed the existing
  canonical completion/organizer flow and the final JAV holding is durable.
- Read the existing canonical subtitle inventory first. If a valid canonical
  Korean sidecar already exists, finish as a no-op/skip and never overwrite it.
- If Korean subtitles are absent, enqueue exactly that title into a durable,
  resumable, idempotent subtitle job that reuses the proven Stage11 generation
  pipeline and Stage12 publication/Jellyfin-recognition safety contracts.
- Subtitle failure must remain isolated from the completed media: it must not
  undo the download, organizer result, holding, metadata, or Jellyfin media
  item.
- Preserve the existing generic evidence-based rules: no title/cue-specific
  production hardcoding, no broad NAS scan, no direct Jellyfin DB write, and
  no unsafe overwrite of existing KO subtitles.
- Avoid duplicate subtitle work when the same completion event is observed
  more than once; the job identity should be tied to the canonical DVD-ID and
  source/media fingerprint.
- The future automation should be event/queue based around the existing
  completion boundary rather than periodically rerunning the closed Stage12
  173-title rollout.

This is the first post-Stage13 implementation priority. Its exact stage name,
queue schema, trigger point, and rollout contract should be frozen only after a
read-only forensic of the current Stage9 completion hook and the reusable
Stage11/Stage12 single-title boundaries.


## 2026-09-28 Stage12 final closure after bounded staging cleanup

### CURRENT STATUS — Stage12 CLOSED / PASS

This top section is the canonical current status. Older handoff sections below
are retained as historical records and do not override this closure result.

- Audited production source HEAD: `9a06e17d2c954d02979660e740a65e4ecb4b835c`
- Final rollout: 173 titles, `PUBLISHED=163`, `UNRESOLVED=10`,
  `FAILED_RETRYABLE=0`, `RUNNING=0`, `PENDING=0`, `GENERATED=0`.
- All 163 published artifact/report bundles passed the existing mechanical,
  hash, and publication-provenance validators. All 163 NAS sidecars matched
  their recorded artifact hashes. Jellyfin GET-only external subtitle
  recognition passed for all 163; refresh and write count was zero.

The bounded manifest mapped every staging entry to a terminal rollout title.
The local Stage12 temporary staging root had 266 directories, 1,652 files, and
126,891,026 bytes before cleanup; it has zero entries, files, and bytes now.
The remote Stage12 bulk runtime root had 266 directories, 1,388 files, and
114,892,516 bytes, including 988 semantic pending response files; it now has
zero directories, files, and pending responses. Both configured roots remain
in place. Local canonical artifact/report inodes did not overlap staging,
remote staging contained no canonical artifact hashes, and rollout event
provenance did not reference staging paths. Cleanup was limited to the
manifested direct children of those two roots.

The 10 unresolved titles and DB reasons are:

- `STAGE12_UNSAFE_AUDIO_TIMELINE` (8): HMN-899 (sequence 7), NIMA-059,
  PRED-889, SGKI-075, SGKI-106, SNOS-334, SVFLA-014, and SW-216 (sequence 5
  for the latter seven).
- `STAGE12_BASELINE_ASR_NO_SPEECH` (1): NHDTC-250 (sequence 9).
- `SUBTITLE_INVENTORY_INVALID` (1): JUR-750 (sequence 1; final transition
  reason `INITIALIZE_FROM_INVENTORY`).

The final runtime audit found no active title, Stage11/Stage12 runner or
controller, locked runner lock, unfinished heartbeat, active remote task,
ASR production temp entry, or large `/tmp` media file. The persistent Hermes
dashboard/gateway processes had no active Stage12 invocation and no working
directory or open file under the remote staging root. Fixture-based Stage11
controller, live runner, semantic retry-feedback, stream redaction, safe
artifact inspector, ASR temp policy, Stage12 batch/retry/bulk/rollout and
reconciliation smokes passed. Compile and `git diff --check` passed.

Safety and privacy decisions remain frozen: deterministic unsafe source audio
timelines and baseline no-speech outcomes are terminal `UNRESOLVED`; no numeric
confidence-only production gate, non-VAD fallback, threshold relaxation,
timeline repair, or title-specific exception was added. Semantic retry
feedback uses only safe validator metadata; Hermes raw output remains
suppressed; artifact inspection is whitelist-only; new durable reports use
session identity fingerprints without raw values.

Historical privacy limitation: 162 legacy published reports still contain
raw session identity fields (486 fields total). The one report using the new
schema contains three SHA-256 identity fingerprints and no raw session field.
The legacy reports were not modified in place during closure.

Stage12 is **CLOSED / PASS**. Stage13 is **NOT STARTED**.

## 2026-09-28 Stage12 rollout-summary wrapper correction

The HMN-896 result-collection wrapper that exited nonzero was an inline
post-run Python snippet, not a tracked repository utility. It imported
`Stage12RolloutStateStore` and `rollout_counts` from
`teddy_discovery_stage12_rollout`; `rollout_counts` is defined in
`teddy_discovery_stage12_bulk_runner`, while the rollout store's existing
public read-only summary API is `Stage12RolloutStateStore.status_counts()`.
The summary path now uses only the canonical rollout module:
`from teddy_discovery_stage12_rollout import Stage12RolloutStateStore`, then
`store.status_counts()`. It does not import the bulk runner or call its
production entry point. Repository search found no duplicate bad import in
other wrappers or utilities. A temporary read-only fixture verified exit 0
and `PUBLISHED=163`, `FAILED_RETRYABLE=0`, `RUNNING=0`, `UNRESOLVED=10`;
Stage12 batch, retry, bulk-runner, rollout smokes, compile, and diff checks
passed. No production state or runner semantics changed.

## 2026-09-28 HMN-896 final explicit retry canary

At expected HEAD `41517e57bc59d3f536644e91ad49c28fb27d26f8`, the read-only
preflight passed: HMN-896 was `FAILED_RETRYABLE` sequence 3 with reason
`STAGE12_SEMANTIC_OUTPUT_VALIDATION_RETRY_EXHAUSTED`, no active rollout
title, production interpreter/dependencies passed, and the source size/mtime
matched Discovery, rollout, baseline ASR, and targeted-evidence fingerprints.
The safe artifact inspector reported 596 baseline segments, 559 semantic
cues, five targeted windows/results, and five `PRESENT_UNRESOLVED` bindings.
The targeted artifact's baseline hash and source fingerprint matched.

The one authorized retry completed as `PUBLISHED` sequence 6 with reason
`STAGE12_PUBLICATION_AND_JELLYFIN_VERIFIED`. Part 5 attempt 1 failed
`CUE_COUNT_MISMATCH` (`expected=64`, `actual=63`), response 7,169 bytes,
SHA-256 `8ba32b248698b661e8dbe013d71bbd1a896c49250bd4a774b865b3ca92220b20`.
Its reconstructed prompt SHA-256 was
`45747d407699b7eaff495b12b4c8179620c6a54c638e2a447b852c6beae4ea28`.
Attempt 2 included machine-generated validation feedback and passed. Its
reconstructed prompt SHA-256 was
`285b2c2d8dd903dfb7f8cfc04237fa79ad5d5a7e9042efd4aeb6443b69a166e8`.
The accepted response bytes were preserved as the canonical part artifact
(5,434 bytes; SHA-256
`f89870a2b0f1adea3f95383995f2d314c80ebb09600ff4b15e865af5ff39417a`). The
part promotion hard-links the validated pending bytes without rewriting them.
No subtitle or transcript content was copied here.

All six Hermes invocations reported raw output suppression. The canary wrapper
captured child stdout/stderr and emitted only allowlisted numeric/enum/hash
diagnostics; no subtitle body, session identifier, staging path, or raw JSON
was forwarded. The new controller report safe summary found zero raw session
identity fields and three SHA-256 fingerprints. Its hash matched rollout
provenance; the CLEAN artifact hash also matched. The final state counts were
`PUBLISHED=163`, `FAILED_RETRYABLE=0`, `RUNNING=0`, `UNRESOLVED=10`, with zero
active titles and zero non-HMN rollout events after the retry began.

The exact local and remote task staging directories were removed after report
and artifact verification; no target staging input remained. `/tmp` and
`/var/tmp` had zero files over 50 MiB, and the Stage12 heartbeat showed
`COMPLETE` with no active DVD. No other title changed.

The outer result-collection wrapper itself exited nonzero after the production
runner had returned exit code 0 because its post-run code imported
`rollout_counts` from the wrong module. Final state, report/artifact hashes,
other-title event count, and cleanup were then verified with separate
read-only checks. No recovery or additional retry was performed.

## 2026-09-28 Safe subtitle-artifact preflight inspection

The HMN-896 read-only forensic command used recursive `rg` with a title
identifier against the artifact directory. The minified targeted-evidence JSON
contained that identifier, so ripgrep emitted its complete matching line,
including subtitle-bearing fields. This was the direct leak source; the
execution wrapper did not redact or truncate matching file lines. `cat`,
`jq` body projections, or Python printing parsed objects have the same unsafe
property if used on subtitle-bearing artifacts. The body was not copied into
this handoff and is not repeated here.

Added `teddy_discovery_safe_artifact_inspector.py`, a read-only JSON inspector
for ASR, targeted evidence, semantic input/output, review, and controller
report artifacts. It parses internally and emits only artifact kind, exists,
byte size, SHA-256, integer schema version, validated public DVD-ID, source
fingerprint match state, cue/segment/source/window/result counts, allowlisted
targeted status counts, part/count metadata, allowlisted route, and raw-session
field/fingerprint counts. It never emits the supplied path, JSON fragments,
free-form strings, or exception text. Malformed JSON reports only
`INVALID_JSON` with safe size/hash metadata. The helper is available for
future Stage11/Stage12 read-only artifact preflight; production validators and
runners were not changed.

Offline smoke passed: sentinel subtitle/session fields and a sentinel session
path were absent from stdout/stderr for targeted evidence, ASR, semantic
input/output, review, and controller-report fixtures; targeted counts, source
fingerprint match, size/hash were exact; malformed input emitted only a safe
error code. Existing ASR/targeted artifact, semantic translator/review,
Stage11 controller, and Stage12 batch/retry/bulk/rollout smokes passed, as did
compile and `git diff --check`. No HMN-896 retry, rollout write, Hermes call,
publication, or Jellyfin write occurred.

## 2026-09-28 Stage11 durable-report session identity privacy fix

Read-only forensic at expected HEAD `d6366666b9b26824602b7e122fb61a11b7d7f7eb`
found raw session identifiers in three nested identity fields in all 133
local durable Stage11 controller reports inspected. Stage11 uses the
translation identity only when validating existing semantic staging; review
identity values are validated for shape. Stage12, publication, Jellyfin,
reconciliation, and rollout provenance use report/artifact paths and hashes,
not these nested identifiers. Raw identifiers remain necessary in memory for
exact semantic part identity validation and review binding; accepted semantic
staging remains separate from the durable controller report.

New controller reports serialize SHA-256 fingerprints for translation,
source-translation, and review-execution session identities, never the raw
identifiers. Existing reports with legacy raw fields remain readable. When
validating a new fingerprint-only report against semantic staging, the
controller finds the unique staging directory whose basename fingerprint
matches, then performs the existing exact raw identity checks in memory.
Validator, prompt, retry, and publication behavior are unchanged. The Stage12
fixture using the legacy report schema remains compatible.

FNS-235's already-published local controller report was left unchanged. Its
report SHA-256 is bound by its rollout row and artifact preflight, and safely
rewriting it would require changing rollout provenance; this task prohibited
rollout DB writes. The report is local to the Stage12 artifact tree, not
copied to the NAS published subtitle directory. The report hash and published
subtitle artifact hash remain distinct. Other scanned local controller
reports have the same legacy schema; no migration was attempted.

Verification passed: controller smoke (51 checks, including fingerprint-only
serialization and completion replay), stateful parts (65 checks), live-runner
and retry/stream smokes, Stage12 batch/retry/bulk/rollout smokes, compile, and
`git diff --check`. No production semantic invocation, rollout mutation,
publication, or Jellyfin write occurred.

Privacy handling note: during the initial forensic work, one tool output
accidentally exposed the FNS session identifier inside a staging path. The
value is intentionally not reproduced here or in source, logs, or commit
metadata. The execution-stream exposure has been acknowledged to the user;
subsequent inspection avoided value-bearing output. This incident does not
change the existing FNS report or rollout provenance.

## 2026-09-27 Stage11 Hermes raw-output stream containment

Forensic at HEAD `80da72bc02a8218d237760dd8d04dbadf13f7a55` found that the
semantic runner already invoked Hermes with `-Q --quiet`, but the GDTM-091
canary still displayed the CLI's raw `review diff`. The installed `hermes chat
--help` describes quiet mode as suppressing banners, spinners, and tool
previews; it exposes no separate raw-diff/output suppression option. Quiet
mode therefore did not protect this path.

The remote Hermes command had no PTY and no stdout/stderr redirection. The
local runner used `subprocess.Popen(..., stdout=PIPE, stderr=PIPE)` and a
selector, then forwarded each received byte chunk unchanged to the matching
parent stdout/stderr stream. The execution interface merged those parent
streams, so the retained evidence cannot establish whether GDTM's raw diff
came from stdout, stderr, or both. No tee or line filter was involved. The
semantic response traveled separately: Hermes wrote the remote pending JSON,
and `_read_remote_regular_file` captured its bytes for validation. Thus CLI
display output was unnecessary for semantic processing.

The GDTM execution stream did expose response text. The runner itself did not
write a raw stdout/stderr log file; the runtime tree had only the heartbeat
and a 70-byte last-run summary log. The accepted semantic response remains
present as a Stage12 staging artifact (part 12: 6,430 bytes); this is the raw
response artifact, distinct from an execution log. No subtitle body was read
back or copied into this handoff. Filesystem inspection cannot establish the
retention policy of the external execution-stream service.

The live runner now captures both CLI streams only in bounded memory, hashes
them, and never forwards their bytes to stdout, stderr, runner logs, or
heartbeat. It emits only stream byte counts/SHA-256 and exact safe remote
status lines carrying a per-invocation random nonce. Nonzero results retain
SSH/model exit codes plus safe stream digests; arbitrary stderr is never
embedded in an exception. Timeout activity detection still observes captured
bytes and retains the existing inactivity/absolute timeout and remote
cleanup behavior. Other captured SSH errors now use byte counts and hashes
instead of raw stderr. The remote pending JSON read used by the validator is
unchanged.

Offline verification passed: stream fixture (raw sentinels absent from
stdout/stderr/execution log; safe diagnostics, error exit codes and timeout
behavior preserved), stateful parts (65/0), controller (39/0), live runner
(16/0), live runner retry, Stage12 batch/retry/bulk/rollout, Python compile,
and `git diff --check`. No Hermes production invocation, rollout write,
publication, Jellyfin write, prompt/validator change, or retry-count change
was made.

## 2026-09-28 SCOP-830 semantic retry-feedback and stream-redaction canary

At expected HEAD `fa68ec685f9379568d8edb3cc22934632681f1c7`, the explicit
single-title retry preflight passed with a clean worktree, production Python
and audio dependencies, `SCOP-830=FAILED_RETRYABLE` sequence 3, zero active
titles, and matching source identity
`SCOP/SCOP-830/SCOP-830.mp4` (1,714,450,031 bytes; mtime_ns
`1788020170245532124`). The only rollout transitions during this canary were
SCOP-830: `FAILED_RETRYABLE -> RUNNING -> GENERATED -> PUBLISHED`, sequences
3 -> 4 -> 5 -> 6.

Part 3 attempt 1 failed `INVALID_KO / KO_CONTROL_CHARACTER` at cue ordinal 36.
Its semantic query UTF-8 SHA-256 was
`b3434294bc8ae497226806c7a05bd65702f46caf0a1dfb84d84c534e77e5a532`; the raw
response was 7,846 bytes with SHA-256
`15c903a08e07b1bea74e52329dc5649d695832d8903877d2f8df517adab9a2ac`.
Attempt 2 included the machine-generated validation feedback. Its query
UTF-8 SHA-256 was
`369516e74474f8fd13e53ae3887846cd7289b3db8e836baf397dec893af6af96`; the
validated response was 7,850 bytes with SHA-256
`cc7cee36932fc4a3f6373717909ef4eed9e0bb9d7ad82c7fbd6656c3351d26fd`.
Attempt 2 passed. All 13 parts completed; final semantic cue count was 786.
No response or subtitle text was copied into this handoff.

Every Hermes call reported `HERMES_RAW_OUTPUT_SUPPRESSED=YES`; stdout/stderr
were represented only by byte counts and SHA-256 digests, plus allowlisted
model/remote exit status. No raw diff or subtitle body appeared in the runner
output, execution stream, or structured heartbeat. The runner does not persist
its stdout/stderr streams. The runtime last-run summary file was 70 bytes; its
contents were not read, so that file is not independently attested here.
Heartbeat ended `COMPLETE`; no active RUNNING/GENERATED title remained. The
published artifact and report were hash-verified, and Jellyfin external
subtitle recognition was verified. Final counts: `PUBLISHED=161`,
`FAILED_RETRYABLE=2`, `RUNNING=0`, `UNRESOLVED=10`. No other title state
changed.

After verifying all 13 remote pending response hashes against the local
canonical parts, the exact per-session remote and local staging copies were
removed (remote/local cleanup PASS; 16 local files, 382,145 bytes removed).
The published artifact and controller report remain in their durable
artifact directory. No other title's staging or runtime data was touched.

## 2026-09-28 FNS-235 retry-feedback canary — session-id report exposure

At expected HEAD `42165a2100bc640042f87ec55f184cf67bf21a30`, read-only
preflight passed with FNS-235 `FAILED_RETRYABLE` sequence 3, zero active
titles, production Python/dependencies, and matching NAS source identity
`FNS/FNS-235/FNS-235.mp4` (3,914,686,408 bytes; mtime_ns
`1788081907263298717`). The retry completed all 10 semantic parts and
publication/Jellyfin verification. Part 7 attempt 1 failed
`SESSION_ID_MISMATCH` at `part.session_id`, response 4,896 bytes with SHA-256
`b7a68314cf662f409ec0fea236bc44a8298661aa91db83c193d07683079cdc62`.
The part-query UTF-8 SHA-256 values were
`aa4ac93df846e9c230cbfd87fc06fa5717e4fef9844f965dc65274209aababba`
(attempt 1) and
`952d23645c6fb03bc9af77bb1ef6663b7627e41a00be09b0a1d7cd0bb414261c`
(attempt 2, with validator feedback). Attempt 2 passed; its accepted response
was 4,896 bytes with SHA-256
`425b4911932e321783cf3b43e022ea1ce2f0e959571ccbba27acf018cf9a4f39`.

The production runner completed `FAILED_RETRYABLE -> RUNNING -> GENERATED ->
PUBLISHED`, sequences 3 -> 4 -> 5 -> 6, with final reason
`STAGE12_PUBLICATION_AND_JELLYFIN_VERIFIED`. The only rollout events during
the canary belonged to FNS-235. Final counts were `PUBLISHED=162`,
`FAILED_RETRYABLE=1`, `RUNNING=0`, `UNRESOLVED=10`; publication and Jellyfin
external visibility were verified.

All five Hermes invocations reported `HERMES_RAW_OUTPUT_SUPPRESSED=YES`. The
canary wrapper captured child stdout/stderr in memory and emitted only
allowlisted fields; it suppressed the runner's session/progress lines, so no
actual session identifier or subtitle body appeared in the user-visible
stdout/stderr or execution stream. Heartbeat and runtime summary had no
session identifier. However, a safe exact-value presence check found the
actual generated session identifier in two fields of the durable Stage11
controller report: `review_result_identity.source_translation_session_id`
and `translation_result_identity.session_id`. The identifier is deliberately
not recorded here. This violates the canary's session-id privacy requirement
even though stream redaction worked. The report and rollout row were not
rewritten; mutating a published artifact and its rollout provenance was
outside this canary's safe completion path.
No other title was run.

The run-specific local staging directory remains (13 files, 239,697 bytes,
zero pending files); remote staging cleanup was not verified after detecting
the report exposure. The heartbeat reached `COMPLETE`, active rollout titles
are zero, and `/tmp` contains no files over 50 MiB. Do not start another title
until the report's session-id emission/storage contract is addressed.

## 2026-09-27 GDTM-091 semantic retry-feedback production canary

At expected HEAD `512e8de3459d440021302674ba0feefcebef2b4b`, read-only
preflight confirmed a clean worktree, `GDTM-091=FAILED_RETRYABLE` sequence 3
with reason `STAGE12_SEMANTIC_OUTPUT_VALIDATION_RETRY_EXHAUSTED`, no active
rollout title, and production interpreter/dependency PASS. Source identity
matched Discovery, rollout, and current NAS: `GDTM/GDTM-091/GDTM-091.mp4`,
2,841,873,974 bytes, mtime_ns `1788070014563915057`.

Part 12 attempt 1 used a 3,022-byte prompt, SHA-256
`df7752671d224f0683ef6e0c62c7ed40c9546a22d86d3bb41bfd374c9dd45522`. It
failed `INVALID_KO`, subcode `KO_CONTROL_CHARACTER`, cue ordinal 2. The
rejected response was 6,440 bytes, SHA-256
`ebba1d7afef8a05056ee16b61c15f979b1434a8db5d7d7e4af2701188513268c`.
Attempt 2 used a 3,245-byte prompt, SHA-256
`64613974408042798e410cdd1ca257b8186e4ca2f5dca11d30e67963cfa0d0df`. The
Hermes prompt record confirms it included the exact safe feedback suffix for
`INVALID_KO`, `KO_CONTROL_CHARACTER`, part 12, cue ordinal 2. It passed
validation. The accepted response payload was 6,430 bytes, SHA-256
`0973216e6c537cc69d86aad1306c78ae96d30e0e27c5403258a89bb404e40de0`.

**Logging disclosure:** the Hermes CLI emitted a raw review diff for the
attempt-1 response to the live execution stream, including subtitle body.
Stage11's own validation diagnostic line contained only safe metadata, and
the retry feedback and this handoff contain no subtitle body. The CLI diff
was not copied into the report or retained in the handoff. Attempt 2 passed;
the runner continued through the remaining Stage11 parts and publication.

The one-title run finished `PUBLISHED`, sequence 6, reason
`STAGE12_PUBLICATION_AND_JELLYFIN_VERIFIED`. Final counts:
`PUBLISHED=160`, `FAILED_RETRYABLE=3`, `RUNNING=0`, `UNRESOLVED=10`. Stage12
selected and processed only GDTM-091; no other title state changed.

The runner exited with heartbeat `COMPLETE` and no active rollout title. No
runner process remained; `/tmp` had no file larger than 100 MiB and `/var/tmp`
had 37,546,962,944 bytes free. Per-session Stage12 staging remains in the
runtime area as run evidence (19 files); it was not manually deleted.

## 2026-09-27 MAAN-1193 semantic retry-feedback production canary

At expected HEAD `0459f77d551273b5166d0227bd67965261d0efd5`, read-only
preflight confirmed a clean worktree, `MAAN-1193=FAILED_RETRYABLE` sequence 5
with reason `STAGE12_SEMANTIC_OUTPUT_VALIDATION_RETRY_EXHAUSTED`, matching
source identity (`MAAN/MAAN-1193/MAAN-1193.mp4`, 2,431,792,344 bytes,
mtime_ns `1788865578276147930`), no active rollout title, and passing
production interpreter/dependency checks.

The authorized single-title retry used the new feedback contract. For part 9,
attempt 1's unchanged base prompt was 3,020 bytes, SHA-256
`10ce370bead05ea1efaaba30c37bc60e674e96727eaa9d372d5a437cffed969a`. It
failed `INVALID_KO`, subcode `KO_EMPTY_OR_WHITESPACE`, cue ordinal 8. The
rejected response was 4,993 bytes, SHA-256
`fc36ea51c15ac83d97dd328c972ab10c9309e21811136900ae4424fd5c55160c`.

Attempt 2 used a 3,244-byte prompt, SHA-256
`61c106f558eb69ba5e419b8d9cff678729287a02afab67a369f842c21650a4ab`. Its
prompt record confirms that it included `INVALID_KO`,
`KO_EMPTY_OR_WHITESPACE`, and ordinal 8 as machine-generated feedback. It
passed validation. The accepted response payload was 5,207 bytes, SHA-256
`a0b76396ec3ffda18d11c010d8157b022d90fc1bb31711fbd65ee2240188550c`. The
feedback/log diagnostics contained no subtitle text or rejected response
body. All ten parts covering 603 cues validated; the complete result SHA-256
was `6584a9a802d510a9afc486b3dbd815bd4994262e78fedb1617d5c82cc49d97b2`.

Stage12 processed exactly one title. `MAAN-1193` finished `PUBLISHED`,
sequence 8, reason `STAGE12_PUBLICATION_AND_JELLYFIN_VERIFIED`. Final counts:
`PUBLISHED=159`, `FAILED_RETRYABLE=4`, `RUNNING=0`, `UNRESOLVED=10`. No other
title was selected or changed.

The runner exited with heartbeat `COMPLETE` and no active rollout title. No
runner process remained; `/tmp` had no file larger than 100 MiB and `/var/tmp`
had 37,550,080,000 bytes free. The Stage12 per-session staging artifacts
(validated semantic parts/input/result) remain in the runtime staging area as
run evidence; no separate audio temporary workspace remained. No recovery or
additional retry was performed.

## 2026-09-27 MAAN-1193 semantic retry contract forensic and fix

Read-only forensic of the MAAN-1193 sequence-5 canary confirmed that part 9's
two failed requests were separate user-message turns in the existing Hermes
session. The profile's read-only message history records them at
2026-09-27 05:11:23.837871 UTC and 05:12:51.278167 UTC. Both prompt messages
were 3,020 bytes with SHA-256
`10ce370bead05ea1efaaba30c37bc60e674e96727eaa9d372d5a437cffed969a`.
The reconstructed base64 CLI query payload was 4,028 bytes with SHA-256
`6228ace347bd1eb3e5e9a17d7094b2cf42e0e0eb2a1cb48694d898d34eda6de8`.
Both requests referenced the same immutable semantic input, SHA-256
`60968f77cc913b1dc40769e3593192a106036693847ce2b6211e76b9fa03e84c`.
The two prompt records had no validation feedback. The runner removed the
first rejected remote pending response before issuing attempt 2, then reused
the same part query and session. No provider request ID was persisted; the
session's aggregate API-call counter cannot identify these two calls. No
explicit temperature or seed was passed by the runner, and the provider's
effective defaults were not recoverable. There is no evidence of local
pending-response reuse or provider caching; caching cannot be ruled out.

Cause: generic retry-contract bug (A). Before this change a validation retry
made a distinct model request but repeated the same prompt without telling the
model what predicate failed. The prompt requires Korean output for each cue
and validator requires nonempty Korean, but it does not state an empty-output
exception for non-speech cues. No direct prompt/validator contradiction was
found. The rejected part-9 cue had a nonempty 9-character Japanese source;
only structural metadata was inspected. Its rejected Korean output and all
other subtitle text remain excluded from this handoff.

The second attempt now appends a machine-generated feedback block built only
from safe validator enums and numeric/location fields. The first attempt's
query is byte-for-byte unchanged. `INVALID_KO` feedback carries its subcode
and cue ordinal; count mismatch carries expected/actual counts; session
mismatch states the required fixed contract location. The feedback includes
no source or rejected response text. Validators, output acceptance, prompt
semantics on the first attempt, and the one-retry limit are unchanged.

Verification passed: stateful parts (65/0), controller (39/0), live runner
(16/0), live runner retry (PASS), Stage12 batch/retry/bulk/rollout (all PASS),
compile, and `git diff --check`. Retry smoke proves the first query is
unchanged, second query and hash differ, safe failure metadata is included,
sentinel subtitle text is absent, and a valid first response does not retry.
No Hermes production invocation, MAAN-1193 retry, rollout DB write,
publication, or Jellyfin write was performed.

## 2026-09-27 MAAN-1193 semantic diagnostic retry canary

At expected HEAD `82d417a450bf881ec926a73fab907400559c254e`, preflight
confirmed a clean worktree, `MAAN-1193=FAILED_RETRYABLE` at sequence 3 with
reason `STAGE12_SEMANTIC_OUTPUT_VALIDATION_RETRY_EXHAUSTED`, no active
`RUNNING`/`GENERATED` titles, and matching Discovery/NAS source identity:
`MAAN/MAAN-1193/MAAN-1193.mp4`, 2,431,792,344 bytes,
mtime_ns `1788865578276147930`. Production Python, NumPy, and PyAV preflight
passed.

The one authorized explicit retry transitioned MAAN-1193 from
`FAILED_RETRYABLE` sequence 3 to `RUNNING` sequence 4, then back to
`FAILED_RETRYABLE` sequence 5 with reason
`STAGE12_SEMANTIC_OUTPUT_VALIDATION_RETRY_EXHAUSTED`. Part 9 failed
`INVALID_KO` on both attempts. Both responses were 4,993 bytes with identical
SHA-256 `fc36ea51c15ac83d97dd328c972ab10c9309e21811136900ae4424fd5c55160c`,
so both attempts returned the same payload. The exact predicate was
`KO_EMPTY_OR_WHITESPACE`, at 1-based cue ordinal 8. No response or subtitle
text, nor session ID, was retained in this handoff.

Final counts remain `PUBLISHED=158`, `FAILED_RETRYABLE=5`, `RUNNING=0`,
`UNRESOLVED=10`. No other title state changed. No artifact/report was
accepted, and publication/Jellyfin were not reached. The runner completed
with one title processed and no active title left behind. Both rejected
remote pending responses were cleaned by the retry path. The private
`/var/tmp` capture was removed after extracting safe diagnostics; `/tmp` had
no files over 100 MiB, `/var/tmp` had 35 GiB free, and 8.5 GiB RAM was
available. A pre-existing Stage11 staging directory remained with content
timestamps predating the canary; it was left intact. No new artifact/report
directory appeared. No recovery or second retry was performed.

## 2026-09-27 Stage11 semantic validation body-free diagnostics

Added generic safe diagnostics for rejected stateful semantic parts without
changing validator predicates, retry count, prompt, or output acceptance. The
validation exception carries its reason code plus safe optional fields for an
`INVALID_KO` subcode and 1-based cue ordinal, cue-count expected/actual values,
or the fixed `part.session_id` location. The Stage11 live runner records the
part number, retry attempt, response byte length, and SHA-256 alongside the
validation code. It no longer logs the session identifier on this rejection
line. No response body or subtitle fields are logged.

`INVALID_KO` output predicates now have distinct safe subcodes:
`KO_REQUIRED`, `KO_NOT_EXACT_STRING`, `KO_EMPTY_OR_WHITESPACE`,
`KO_TEXT_LIMIT`, `KO_CONTROL_CHARACTER`, and `KO_RUNAWAY_REPETITION`.
Existing source-cue integrity predicates retain `INVALID_KO` and carry separate
source-cue subcodes; an unrecognized legacy path is marked
`INVALID_KO_UNCLASSIFIED`. Ordinals are 1-based within the part.

Offline verification passed: stateful parts smoke (65 PASS / 0 FAIL), live
runner retry smoke (including body-sentinel redaction and payload digest),
stateful controller smoke (39 PASS / 0 FAIL), live runner smoke (16 PASS / 0
FAIL), Stage12 batch, retry, bulk runner, and rollout smokes, Python compile,
and `git diff --check`. No Hermes invocation, production retry, rollout DB
write, publication, or Jellyfin write was performed.

## 2026-09-26 SW-216 explicit retry production canary

Before retry, SW-216 was `FAILED_RETRYABLE`, sequence 3, reason
`STAGE12_TITLE_FAILURE`; counts were `PUBLISHED=158`,
`FAILED_RETRYABLE=6`, `RUNNING=0`, `UNRESOLVED=9`. The canonical replay
recorded the **production fail point** at frame 438 / PTS 457,093: signed
peak drift 66.292 ms exceeded the 64 ms three-decoded-frame bound. Separately,
the full replay EOF diagnostic showed signed drift +63.738 s and corrected
EOF sample mismatch −1. Maximum single-frame correction was 21.313 ms (one
decoded-frame duration); the recorded fail point was cumulative peak drift,
not an EOF failure. The replay procedure recorded matching source
path/size/mtime against rollout identity. Current NAS source matched:
`SW/SW-216/SW-216.mp4`, 4,172,018,393 bytes, mtime_ns
`1788082693280273595`. No duplicate/backward PTS violation was recorded.

At expected production HEAD
`22f5e75d338fa6b80356de23e465037c6fcc721e`, the single explicit retry passed
production interpreter, clean worktree, expected sequence, exact source
identity, and zero-active-title preflights. It transitioned
`FAILED_RETRYABLE -> RUNNING -> UNRESOLVED`, sequence `3 -> 4 -> 5`.
Production reproduced `ASRAudioUnsafeTimelineError: peak net sample-clock
drift exceeds three decoded frames`; Stage12 recorded reason
`STAGE12_UNSAFE_AUDIO_TIMELINE` and outcome `UNSAFE_AUDIO_TIMELINE`. Final
counts are `PUBLISHED=158`, `FAILED_RETRYABLE=5`, `RUNNING=0`,
`UNRESOLVED=10`.

No baseline artifact/report was stored. The typed Stage11 failure stopped
before external subtitle evidence lookup/alignment and publication/Jellyfin.
Only SW-216 was selected; no other title was processed. Temporary ASR
cleanup reported PASS; the production temp root was empty afterward, `/tmp`
had no files over 100 MiB, `/var/tmp` had 35 GiB free, and 8.5 GiB RAM was
available. No recovery or second retry was performed.

## 2026-09-26 SNOS-334 explicit retry production canary

Before retry, SNOS-334 was `FAILED_RETRYABLE`, sequence 3, reason
`STAGE12_TITLE_FAILURE`; counts were `PUBLISHED=158`,
`FAILED_RETRYABLE=7`, `RUNNING=0`, `UNRESOLVED=8`. The canonical full replay
recorded cumulative peak signed drift +12.322 s beyond the existing
three-decoded-frame bound at frame 2,323 / PTS 2,390,035, corrected EOF
sample mismatch 0, and maximum single-frame correction 0.667 ms. The replay
procedure recorded matching source path/size/mtime against rollout identity.
Current NAS source matched that identity: `SNOS/SNOS-334/SNOS-334.mp4`,
4,404,422,746 bytes, mtime_ns `1788083516029248371`. The replay identified
the cumulative peak as the fail point; it recorded no duplicate/backward PTS
or per-frame correction bound violation.

At expected production HEAD
`f476e2a8ca377fbd8507a9d871dd236a77d935c1`, the single explicit retry passed
production interpreter, clean worktree, expected sequence, exact source
identity, and zero-active-title preflights. It transitioned
`FAILED_RETRYABLE -> RUNNING -> UNRESOLVED`, sequence `3 -> 4 -> 5`.
Production reproduced `ASRAudioUnsafeTimelineError: peak net sample-clock
drift exceeds three decoded frames`; Stage12 recorded reason
`STAGE12_UNSAFE_AUDIO_TIMELINE` and outcome `UNSAFE_AUDIO_TIMELINE`. Final
counts are `PUBLISHED=158`, `FAILED_RETRYABLE=6`, `RUNNING=0`,
`UNRESOLVED=9`.

No baseline artifact/report was stored. The typed Stage11 failure stopped
before external subtitle evidence lookup/alignment and publication/Jellyfin.
Only SNOS-334 was selected; no other title was processed. Temporary ASR
cleanup reported PASS; the production temp root was empty afterward, `/tmp`
had no files over 100 MiB, `/var/tmp` had 35 GiB free, and 8.5 GiB RAM was
available. No recovery or second retry was performed.

## 2026-09-26 SGKI-106 explicit retry production canary

Before retry, SGKI-106 was `FAILED_RETRYABLE`, sequence 3, reason
`STAGE12_TITLE_FAILURE`; counts were `PUBLISHED=158`,
`FAILED_RETRYABLE=8`, `RUNNING=0`, `UNRESOLVED=7`. The canonical full replay
recorded cumulative peak signed drift +20.141 s beyond the existing
three-decoded-frame bound at frame 1,294 / PTS 1,341,904, corrected EOF
sample mismatch 0, and maximum single-frame correction 0.667 ms. The replay
procedure recorded matching source path/size/mtime against rollout identity.
Current NAS source matched that identity: `SGKI/SGKI-106/SGKI-106.mp4`,
4,898,003,063 bytes, mtime_ns `1788274311454167056`. The replay identified
the cumulative peak as the fail point; it recorded no duplicate/backward PTS
or per-frame correction bound violation.

At expected production HEAD
`bd52ae98ac4848480e31791316868aad4ad6d635`, the single explicit retry passed
production interpreter, clean worktree, expected sequence, exact source
identity, and zero-active-title preflights. It transitioned
`FAILED_RETRYABLE -> RUNNING -> UNRESOLVED`, sequence `3 -> 4 -> 5`.
Production reproduced `ASRAudioUnsafeTimelineError: peak net sample-clock
drift exceeds three decoded frames`; Stage12 recorded reason
`STAGE12_UNSAFE_AUDIO_TIMELINE` and outcome `UNSAFE_AUDIO_TIMELINE`. Final
counts are `PUBLISHED=158`, `FAILED_RETRYABLE=7`, `RUNNING=0`,
`UNRESOLVED=8`.

No baseline artifact/report was stored. The typed Stage11 failure stopped
before external subtitle evidence lookup/alignment and publication/Jellyfin.
Only SGKI-106 was selected; no other title was processed. Temporary ASR
cleanup reported PASS; the production temp root was empty afterward, `/tmp`
had no files over 100 MiB, `/var/tmp` had 35 GiB free, and 8.5 GiB RAM was
available. No recovery or second retry was performed.

## 2026-09-26 SGKI-075 explicit retry production canary

Before retry, SGKI-075 was `FAILED_RETRYABLE`, sequence 3, reason
`STAGE12_TITLE_FAILURE`; counts were `PUBLISHED=158`,
`FAILED_RETRYABLE=9`, `RUNNING=0`, `UNRESOLVED=6`. The canonical full replay
recorded cumulative peak signed drift +21.554 s beyond the existing
three-decoded-frame bound at frame 1,275 / PTS 1,305,616, corrected EOF
sample mismatch −1, and maximum single-frame correction 0.667 ms. The replay
procedure recorded matching source path/size/mtime against rollout identity.
Current NAS source matched that identity: `SGKI/SGKI-075/SGKI-075.mp4`,
4,714,099,215 bytes, mtime_ns `1788055869233598097`. The replay identified
the cumulative peak as the fail point; it recorded no duplicate/backward PTS
or per-frame correction bound violation.

At expected production HEAD
`d7b850516b869d72e2c33bd6616c068d9c2410ef`, the single explicit retry passed
production interpreter, clean worktree, expected sequence, exact source
identity, and zero-active-title preflights. It transitioned
`FAILED_RETRYABLE -> RUNNING -> UNRESOLVED`, sequence `3 -> 4 -> 5`.
Production reproduced `ASRAudioUnsafeTimelineError: peak net sample-clock
drift exceeds three decoded frames`; Stage12 recorded reason
`STAGE12_UNSAFE_AUDIO_TIMELINE` and outcome `UNSAFE_AUDIO_TIMELINE`. Final
counts are `PUBLISHED=158`, `FAILED_RETRYABLE=8`, `RUNNING=0`,
`UNRESOLVED=7`.

No baseline artifact/report was stored. The typed Stage11 failure stopped
before external subtitle evidence lookup/alignment and publication/Jellyfin.
Only SGKI-075 was selected; no other title was processed. Temporary ASR
cleanup reported PASS; the production temp root was empty afterward, `/tmp`
had no files over 100 MiB, `/var/tmp` had 35 GiB free, and 8.5 GiB RAM was
available. No recovery or second retry was performed.

## 2026-09-26 PRED-889 explicit retry production canary

Before retry, PRED-889 was `FAILED_RETRYABLE`, sequence 3, reason
`STAGE12_TITLE_FAILURE`; counts were `PUBLISHED=158`,
`FAILED_RETRYABLE=10`, `RUNNING=0`, `UNRESOLVED=5`. The canonical replay
recorded cumulative peak signed drift +17.942 s beyond the existing
three-decoded-frame bound at frame 1,780 / PTS 1,847,728, corrected EOF
sample mismatch 0, and maximum single-frame correction 0.667 ms. The replay
procedure recorded matching source path/size/mtime against rollout identity.
Current NAS source matched that identity: `PRED/PRED-889/PRED-889.mp4`,
3,586,684,183 bytes, mtime_ns `1788071473288888127`. The replay identified
the cumulative peak as the fail point; it recorded no duplicate/backward PTS
or per-frame correction bound violation.

At expected production HEAD
`6b4bec621feecbd63a2d1d588908fdfdb3f5556e`, the single explicit retry passed
production interpreter, clean worktree, expected sequence, exact source
identity, and zero-active-title preflights. It transitioned
`FAILED_RETRYABLE -> RUNNING -> UNRESOLVED`, sequence `3 -> 4 -> 5`.
Production reproduced `ASRAudioUnsafeTimelineError: peak net sample-clock
drift exceeds three decoded frames`; Stage12 recorded reason
`STAGE12_UNSAFE_AUDIO_TIMELINE` and outcome `UNSAFE_AUDIO_TIMELINE`. Final
counts are `PUBLISHED=158`, `FAILED_RETRYABLE=9`, `RUNNING=0`,
`UNRESOLVED=6`.

No baseline artifact/report was stored. The typed Stage11 failure stopped
before external subtitle evidence lookup/alignment and publication/Jellyfin.
Only PRED-889 was selected; no other title was processed. Temporary ASR
cleanup reported PASS; the production temp root was empty afterward, `/tmp`
had no files over 100 MiB, `/var/tmp` had 35 GiB free, and 8.5 GiB RAM was
available. No recovery or second retry was performed.

## 2026-09-26 HMN-899 explicit retry production canary

Before retry, HMN-899 was `FAILED_RETRYABLE`, sequence 5, reason
`STAGE12_TITLE_FAILURE`; counts were `PUBLISHED=158`,
`FAILED_RETRYABLE=11`, `RUNNING=0`, `UNRESOLVED=4`. The canonical full replay
recorded the unsafe peak crossing at frame 1,690 / PTS 1,730,560, peak signed
drift +20.218 s, corrected EOF mismatch −1 sample, and maximum single-frame
correction 0.667 ms. The replay procedure recorded matching source
path/size/mtime against rollout identity. Current NAS source matched that
identity: `HMN/HMN-899/HMN-899.mp4`, 3,847,055,679 bytes, mtime_ns
`1788055221873611116`. No duplicate/backward PTS or per-frame correction
bound violation was indicated; the recorded fail point was the cumulative
peak-drift bound.

At expected production HEAD
`99e12455030a8b681efa1c2499d465eace4aedfa`, the single explicit retry passed
production interpreter, clean worktree, expected sequence, source identity,
and zero-active-title preflights. It transitioned
`FAILED_RETRYABLE -> RUNNING -> UNRESOLVED`, sequence `5 -> 6 -> 7`.
Production reproduced `ASRAudioUnsafeTimelineError: peak net sample-clock
drift exceeds three decoded frames`; Stage12 recorded reason
`STAGE12_UNSAFE_AUDIO_TIMELINE` and outcome `UNSAFE_AUDIO_TIMELINE`. Final
counts are `PUBLISHED=158`, `FAILED_RETRYABLE=10`, `RUNNING=0`,
`UNRESOLVED=5`.

No baseline artifact/report was stored. The typed Stage11 failure stopped
before external subtitle evidence lookup/alignment and publication/Jellyfin.
Only HMN-899 was selected; no other title was processed. Temporary ASR
cleanup reported PASS; the production temp root was empty afterward, `/tmp`
had no files over 100 MiB, `/var/tmp` had 35 GiB free, and 8.5 GiB RAM was
available. No recovery or second retry was performed.

## 2026-09-26 NIMA-059 explicit retry production canary

Before retry, NIMA-059 was `FAILED_RETRYABLE`, sequence 3, with reason
`STAGE12_TITLE_FAILURE`; counts were `PUBLISHED=158`,
`FAILED_RETRYABLE=12`, `RUNNING=0`, `UNRESOLVED=3`. The canonical replay
record showed a deterministic peak signed drift beyond the existing
three-decoded-frame bound at frame 192,407 / PTS 197,029,183, corrected EOF
sample mismatch 0, and a maximum single correction of 20.833 µs. Its replay
procedure recorded matching source path/size/mtime against rollout identity.
The current NAS source matched that identity: path
`NIMA/NIMA-059/NIMA-059.mp4`, 3,046,116,440 bytes, mtime_ns
`1788070334697909916`. The recorded original EOF reconciliation failure was
therefore consistent with the replay's earlier unsafe-peak finding; no
duplicate/backward or over-one-frame correction was identified.

At expected production HEAD
`81b2657ea53ab88e7fac631a66271065f16306d3`, the single explicit retry passed
production interpreter, clean worktree, expected sequence, exact source
identity, and zero-active-title preflights. It transitioned
`FAILED_RETRYABLE -> RUNNING -> UNRESOLVED`, sequence `3 -> 4 -> 5`. Production
reproduced `ASRAudioUnsafeTimelineError: peak net sample-clock drift exceeds
three decoded frames`; Stage12 recorded reason
`STAGE12_UNSAFE_AUDIO_TIMELINE` and outcome `UNSAFE_AUDIO_TIMELINE`. Final
counts are `PUBLISHED=158`, `FAILED_RETRYABLE=11`, `RUNNING=0`,
`UNRESOLVED=4`.

No baseline artifact/report was stored. The typed Stage11 failure stopped
before external subtitle evidence lookup/alignment and publication/Jellyfin.
The immutable selection contained only NIMA-059, with no other title
processed. Temporary ASR cleanup reported PASS; the production ASR temp root
was empty afterward, `/tmp` had no files over 100 MiB, `/var/tmp` had 35 GiB
free, and 8.5 GiB RAM was available. No recovery or second retry was
performed.

## 2026-09-26 SVFLA-014 explicit retry production canary

At expected production HEAD
`5bb175dd655f24af9d6695e4e0e1424e60be269d`, the authorized one-title retry
passed production interpreter, exact repository/worktree, rollout sequence,
source fingerprint, and zero-active-title preflights. The source fingerprint
matched at 8,577,682,550 bytes and mtime_ns `1788086386432050851`. The
8,577,682,550-byte source was copied under the disk-backed
`/var/tmp/teddy-stage11-asr-production` root; temp capacity preflight passed.

SVFLA-014 transitioned `FAILED_RETRYABLE -> RUNNING -> UNRESOLVED`, sequence
`3 -> 4 -> 5`. Full-title processing reproduced the unsafe timeline at the
existing three-decoded-frame bound: `ASRAudioUnsafeTimelineError`,
“peak net sample-clock drift exceeds three decoded frames.” Stage12 recorded
reason `STAGE12_UNSAFE_AUDIO_TIMELINE` and outcome
`UNSAFE_AUDIO_TIMELINE`. Final counts are `PUBLISHED=158`,
`FAILED_RETRYABLE=12`, `RUNNING=0`, `UNRESOLVED=3`.

The typed Stage11 failure stopped before baseline artifact persistence,
external subtitle evidence lookup/alignment, and publication/Jellyfin. The
rollout row has null artifact/report paths and hashes. The explicit immutable
selection contained only SVFLA-014; no other title was processed. Temporary
ASR cleanup reported PASS; the configured temp root was empty afterward,
`/tmp` had no files over 100 MiB, `/var/tmp` had 35 GiB free, and 8.5 GiB RAM
was available. No recovery or second retry was performed.

## 2026-09-26 deterministic unsafe audio timeline rollout semantics

Added `ASRAudioUnsafeTimelineError`, a narrow subtype of
`ASRAudioValidationError`. The audio canonicalizer raises it only for
deterministic source PTS invariants that make baseline timestamps unsafe:
duplicate/backward raw PTS, a per-frame correction beyond one decoded frame,
or peak signed net drift beyond the existing three-frame bound. The bound,
silence handling, and timestamp correction behavior are unchanged.

Stage11 lets this exception propagate from baseline transcription. Baseline
artifact persistence happens only after transcription returns, so this outcome
creates no baseline artifact and stops before external subtitle lookup or
alignment, targeted evidence, translation, or CLEAN materialization. External
subtitle evidence cannot bypass the unsafe baseline timeline.

Stage12 records the typed outcome as `RUNNING -> UNRESOLVED`, reason
`STAGE12_UNSAFE_AUDIO_TIMELINE`, with `stage11_outcome=UNSAFE_AUDIO_TIMELINE`.
It does not publish or query Jellyfin; batch processing can continue with the
next selected title. UNRESOLVED has no retry transition. Other
`ASRAudioValidationError` and `ASRAudioError` cases remain on their existing
retryable title path; the change does not make all audio validation errors
terminal.

Typed source-read (`ASRSourceError`), Whisper transport/protocol
(`ASRWhisperError`), and Stage11 deployment transport failures are title-scoped
`FAILED_RETRYABLE` outcomes. Unclassified deployment failures and unexpected
programming exceptions remain systemic. Existing typed worker timeout and
pending-artifact retry behavior is unchanged.

Audio, Stage11 controller, Stage12 batch, explicit retry, bulk runner, rollout,
deployment, ASR source, Whisper, and full-title transcriber smokes passed under
`/opt/stage11-stt-venv/bin/python`; compile and `git diff --check` passed. No
SVFLA-014 retry or production state change was performed. It remains
`FAILED_RETRYABLE`, sequence 3, with rollout counts
`PUBLISHED=158`, `FAILED_RETRYABLE=13`, `RUNNING=0`, `UNRESOLVED=2`. A later
authorized retry against the same unsafe source will resolve to UNRESOLVED
under this code. No title-specific branch or media repair was added.

## 2026-09-26 NHDTC-250 explicit retry production canary

At expected production HEAD
`ec021dfe356e6b9bd299764dc0bece5fcf3302a7`, the single-title explicit retry
passed the production interpreter, exact source identity, expected sequence,
and zero-active-title preflights. NHDTC-250 transitioned
`FAILED_RETRYABLE -> RUNNING`, sequence `7 -> 8`. The 6,618,791,523-byte
source copied to the configured temporary ASR root and full-title audio
processing completed through end-of-audio; every processed chunk's ASR call
returned normally and the aggregate had zero segments. Stage11 raised the
typed `FullTitleASRNoSpeechError`; this was not a systemic failure.

Stage12 recorded `RUNNING -> UNRESOLVED`, sequence `8 -> 9`, reason
`STAGE12_BASELINE_ASR_NO_SPEECH`, with `stage11_outcome=NO_SPEECH` and
`error_type=FullTitleASRNoSpeechError`. Final counts are `PUBLISHED=158`,
`FAILED_RETRYABLE=13`, `RUNNING=0`, `UNRESOLVED=2`. No baseline/report
artifact was created; publication and Jellyfin were not run. The retry
selected exactly one title, and the rollout event log has zero other-title
events since its start.

ASR temporary cleanup reported PASS and the production ASR temp root was
empty afterward. `/tmp` usage was 78 MiB (1%); available RAM was 8.5 GiB.
The retry process had exited, with no follow-up recovery or retry performed.

## 2026-09-26 Full-title ASR no-speech semantics and human ground truth

The five bounded NHDTC-250 targeted direct-Whisper audio clips were reviewed
by a human against the source. All five contain no human conversation;
non-speech vocalizations such as groans are present. The targeted segments are
therefore hallucinated/non-speech transcriptions, not speech evidence. One
segment had apparently favorable metrics (`avg_logprob=-0.063856`,
`no_speech_prob=0.160400`) despite having no speech. Numeric-only confidence
gates are not a safe production fix. Do not add non-VAD Whisper fallback when
VAD returns zero, and do not lower/loosen VAD thresholds.

Generic Stage11 policy: a full-title run that successfully decodes and submits
at least one audio chunk, completes all Whisper calls without transport or
protocol errors, and aggregates zero validated speech segments is a typed
`FullTitleASRNoSpeechError` outcome. An empty decoded-chunk stream remains a
contract/source failure. Decode, source transfer, worker, network, and
protocol errors retain their existing error paths. ASR result/artifact
non-empty validators stay strict.

Stage11 requires a non-empty baseline ASR result before it persists the
baseline, checks external JA subtitles, aligns evidence, or enters semantic
translation/review. External JA alignment also requires that ASR result, so
there is no safe existing continuation when baseline ASR has zero segments.
With an external JA subtitle present, Stage11 stops before querying it; with
one absent, it stops at the same boundary. Stage12 records this typed outcome
as terminal `UNRESOLVED` (`stage11_result=NO_SPEECH`, reason
`STAGE12_BASELINE_ASR_NO_SPEECH`), skips publication/Jellyfin, and continues
other titles in the batch. Repeating the same full-title inference is not
useful; no-speech is not `FAILED_RETRYABLE`. Real source/decode/transport/
worker/protocol failures keep their existing title/systemic classification.

## 2026-09-24 Targeted ASR numeric-only diagnostic contract

Added the explicit VM122 endpoint
`/v1/asr/transcribe-targeted-diagnostic` and
`RemoteFasterWhisperASR.transcribe_targeted_chunk_diagnostics()`. It runs the
existing whole-window, no-VAD targeted inference with unchanged model options.
The separate strict response carries only segment timestamps,
`avg_logprob`, `no_speech_prob`, `compression_ratio`, and `temperature`, plus
bounded request identity/count fields. It cannot carry transcript, word, or
token fields. The existing targeted endpoint and response schema are
unchanged; existing callers do not opt in and continue using the original
decoder.

The worker/remote protocol smokes verify unchanged normal targeted responses,
numeric-only diagnostics, and fail-closed rejection of text-bearing,
non-finite, and count-inconsistent diagnostic responses. GPU worker, remote
ASR, targeted second-evidence, Stage11 controller, compile, and `git diff
--check` passed under `/opt/stage11-stt-venv/bin/python`. The implementation
was committed and pushed as `6654fb6b018a25faa2cf0517ef3ebd5542ea3a74`.

VM122's previous worker and remote module hashes were
`ddb39a490d0a44a04d72b51293dea541dc7be4ab212b083fa5b16b336358f927` and
`e3fabce4890b14b4c006a2f67f7a12895d3af0b4ae8e6dc32a0a9735d3dd67b0`.
After exact old-hash checks, the modules were atomically replaced with
`a8df232ba220ae15d736137545e90f3c3bae7cb2432e5cc062688c76ad58e619` and
`0c68f7a7ed28da08cb3bd353e5f32daccd018cbb592e61d79678800ae579bfe8`.
The existing worker launcher and environment were retained; PID 97869 logged
`WORKER_READY`, owns port 8091, and serves both targeted routes. A valid legacy
targeted request using the original NHDTC-250 30–90-second PCM returned one
segment. Both old and new routes also rejected an empty invalid request with
HTTP 413. The numeric endpoint returned four bounded responses: three
NHDTC-250 windows and the FC2-PPV-4575470 control. No transcript text was
printed or saved.

All four full-decode PCM SHA-256 values matched the previously verified
windows exactly. NHDTC-250 segments (start/end are source milliseconds) were:

| Window (s) | Segment | Start–end (ms) | avg_logprob | no_speech_prob | compression_ratio | temperature |
|---|---:|---:|---:|---:|---:|---:|
| 30–90 | 1 | 88,940–89,980 | -0.664063 | 0.845703 | 0.857143 | 0 |
| 5,550–5,610 | 1 | 5,550,000–5,556,000 | -0.805990 | 0.821777 | 0.700000 | 0 |
| 5,550–5,610 | 2 | 5,583,020–5,596,780 | -0.063856 | 0.160400 | 0.700000 | 0 |
| 10,920–10,980 | 1 | 10,925,060–10,932,400 | -0.670573 | 0.742676 | 0.700000 | 0 |
| 10,920–10,980 | 2 | 10,956,880–10,979,980 | -0.580078 | 0.177124 | 0.600000 | 0 |

The FC2-PPV-4575470 30–90-second control returned 23 segments. Its numeric
score clusters were: segments 1–10 `avg_logprob=-0.283995`,
`no_speech_prob=0.386719`, `compression_ratio=1.656827`; segments 11–22
`-0.296944`, `0.005554`, `3.726141`; segment 23 `-0.216688`, `0.007515`,
`1.000000`. Temperature was 0 for all 23. NHDTC-250 therefore has a mixed
confidence profile: three segments have high no-speech probability and weaker
log probability, while two are materially better. This is **C**; the bounded
scores do not by themselves establish whether the weak segments are
hallucinations. Any later targeted-evidence fallback needs a generic,
validated confidence gate before it is trusted.

Both per-request source copies were on `/var/tmp` ext4, used one at a time,
and were removed successfully. `/tmp` remained 78 MiB; local available RAM was
8.4 GiB. VM122 returned to 3.9 GiB available RAM and 3.4 GiB free GPU memory;
the worker remained healthy. A read-only rollout query still showed
NHDTC-250 `FAILED_RETRYABLE`, sequence 7, with counts
`PUBLISHED=158`, `FAILED_RETRYABLE=14`, `RUNNING=0`, `UNRESOLVED=1`.
No rollout, publication, Stage11 controller, NAS, or Jellyfin writes occurred.

## 2026-09-24 NHDTC-250 full-title ASR empty result and recovery

At clean production HEAD `6e263d5dc35267a143b1cbeb6ff978d9b55fdcda`,
NHDTC-250's explicit retry reached EOF after full-media decode,
sample-clock canonicalization and source-end validation passed. The
transcriber then raised `FullTitleASRError: full-title ASR produced no speech
segments` at `teddy_discovery_asr_transcriber.py:420` because the validated
aggregate was empty. The iterator uses 600-second chunks. The preceding
read-only full replay recorded 178,315,129 output samples, yielding 19 chunks
(18 full chunks and a final partial chunk); the transcriber calls the remote
adapter once for each chunk and completed the loop before raising.

The production adapter returns decoded remote segments directly, and local
segment validation returns the tuple unchanged or raises; it does not filter
segments. Remote transport, HTTP and response-protocol errors also raise and
are not converted to empty success. Therefore this execution is classified
**A1 at the application boundary**: all 19 calls completed with zero segments
in aggregate (raw 0, accepted 0, rejected 0). The remote worker can return an
HTTP 200 response with `segments=[]` when VAD finds no regions. VM122's worker
log contains only its Sep 10 startup line; success requests are not logged, and
there is no per-request response/VAD count for this run. Its logs therefore do
not independently confirm each response or whether the audio was actually
silent. Existing PUBLISHED artifacts using the same large-v3 engine contain
275 segments for `FC2-PPV-4575470` and 404 for `SIRO-4448`; no transcript text
was copied into this note. NHDTC-250 produced no baseline artifact, and the
failure occurred before publication/Jellyfin.

Minimum generic diagnostics for a future run: chunk count, remote call count,
successful remote call count, raw/accepted/rejected segment counts, and the
first/last accepted timestamps. Keep transcript and subtitle text out of logs;
do not change systemic/title-local classification based on this incident.

The official `--mode recover-retry` path revalidated the Discovery/NAS source
identity and recovered only NHDTC-250, `RUNNING -> FAILED_RETRYABLE`, sequence
`6 -> 7`, reason `STAGE12_EXPLICIT_RETRY_CRASH_RECOVERY`, at
`2026-09-24T01:09:35.359448+00:00`. Counts are `PUBLISHED=158`,
`FAILED_RETRYABLE=14`, `RUNNING=0`, `UNRESOLVED=1`; the active-title set is
empty and the only new rollout event is NHDTC-250. No retry, Stage11, remote
ASR, publication, or Jellyfin write was performed during recovery. The
production ASR temp directory is empty, `/tmp` remains 78 MiB, `/var/tmp` is
the disk-backed `/dev/loop4` with 36 GiB available, and available RAM is 8.5
GiB.

## 2026-09-24 Stage12 production interpreter guard and explicit-retry recovery

Stage12 now fails closed before any PENDING bulk or explicit retry state
transition unless the process is launched by
`/opt/stage11-stt-venv/bin/python`, its resolved virtualenv prefix matches
`/opt/stage11-stt-venv`, and imports of local audio runtime dependencies
`numpy` and `av` succeed. The guard records `sys.executable`, its realpath,
prefix, and dependency results. Preflight-only CLI modes use the same guard.
This prevents another retry launched as system `python3` from reaching Stage11
or performing NAS/Jellyfin writes. The exact historical retry command below
now uses the production venv interpreter.

The generic `--mode recover-retry` path recovers only an explicitly selected
single stranded explicit retry from `RUNNING` to `FAILED_RETRYABLE`. It
requires the dedicated
`TEDDY_STAGE12_EXPLICIT_RETRY_RECOVERY_AUTHORIZED=YES_I_HAVE_REVIEWED_THE_SINGLE_TITLE`
authorization, one `--dvd-id`, expected sequence, exact clean HEAD, and the
singleton runner lock. It requires that title to be the only active
RUNNING/GENERATED title; verifies the Discovery/NAS path, source size and
mtime against rollout identity; checks artifact/publication absence and that
the latest event is exactly `FAILED_RETRYABLE -> RUNNING` with reason
`STAGE12_EXPLICIT_RETRY_START`; and uses a sequence plus previous-event CAS.
The audited recovery reason is
`STAGE12_EXPLICIT_RETRY_CRASH_RECOVERY`. Existing `recover_running()` remains
unchanged and still means `RUNNING -> PENDING` for ordinary crash recovery.
This recovery is an explicit operator action after a stranded retry; it does
not change Stage12's title-local/systemic exception classification or the
bounded exception-chain diagnostics added after the canary failure.

The recovery smoke covers authorization, exact selector, wrong status,
sequence, start event, source drift, other active titles, other-title state
invariance, the audited transition, and unchanged ordinary crash recovery.
Stage12 retry/batch/bulk/rollout/reconciliation, ASR audio/source/transcriber
and temp policy, Stage11 controller/deployment/live adapters, compile, and
`git diff --check` pass under the production venv.

After commit `c6ebe093d23578c118cb2b649fd44007d5ba1fa3` was pushed and its
clean HEAD/worktree rechecked, the authorized `recover-retry` path verified
the exact source identity/fingerprint and recovered NHDTC-250 only:
`RUNNING -> FAILED_RETRYABLE`, sequence `4 -> 5`, reason
`STAGE12_EXPLICIT_RETRY_CRASH_RECOVERY`, event time
`2026-09-23T23:51:04.881089+00:00`. Counts are now
`PUBLISHED=158`, `FAILED_RETRYABLE=14`, `RUNNING=0`, `UNRESOLVED=1`.
The only rollout event in the recovery interval was NHDTC-250's sequence-5
event; no other title state changed. No retry, Stage11, Remote ASR, NAS write,
or Jellyfin write ran. Do not run `--mode retry` without a separate operator
authorization.

Recovery command shape (fill `--expected-head` only with the reviewed clean
commit after push):

```sh
TEDDY_STAGE12_EXPLICIT_RETRY_RECOVERY_AUTHORIZED=YES_I_HAVE_REVIEWED_THE_SINGLE_TITLE \
  /opt/stage11-stt-venv/bin/python /opt/missav-pwa-subtitle-stage11/teddy_discovery_stage12_bulk_runner.py \
  --mode recover-retry --batch-size 1 --max-titles 1 \
  --dvd-id <exact-dvd-id> --expected-sequence <current-sequence> \
  --expected-head <exact-clean-authorized-HEAD>
```

## 2026-09-23 NHDTC-250 explicit retry systemic failure

At production canary HEAD `31db7b4da48e8841d5a33bde7c00ed1363c4c4b2`,
the explicitly authorized retry for `NHDTC-250` passed preflight, copied the
6,618,791,523-byte source into the configured disk-backed ASR temp root, then
stopped during Stage11 baseline ASR before a baseline ASR artifact was
created. Stage12 recorded `FAILED_RETRYABLE -> RUNNING`, sequence `3 -> 4`,
reason `STAGE12_EXPLICIT_RETRY_START`. The runner returned
`Stage12BatchSystemicError: unexpected Stage11 title execution exception`;
the existing saved heartbeat/CLI output did not preserve the original
low-level exception, so its type/message cannot be recovered from the
available production logs. Available evidence places the failure after source
copy and before baseline ASR artifact persistence. No publication or Jellyfin
stage was reached. Remote ASR request success cannot be determined from the
retained logs.

The request temp directory was cleaned. At the end of the canary,
`/tmp` usage was about 78 MiB, available RAM about 8.5 GiB, and no runner or
ffmpeg process remained. No other title state changed. The authoritative
rollout snapshot was `PUBLISHED=158`, `FAILED_RETRYABLE=13`, `RUNNING=1`,
`UNRESOLVED=1`, with `NHDTC-250=RUNNING`, sequence 4, reason
`STAGE12_EXPLICIT_RETRY_START`.

Diagnostic-only fix: Stage12 now persists a bounded exception-chain summary
with exception types and source locations at the systemic Stage11 wrapper.
Only controlled ASR exception messages are included; arbitrary exception
messages remain in-process to avoid storing subtitle text. The original
exception remains chained, systemic classification is unchanged, and this
does not broaden title-local failure isolation. Batch and explicit-retry
smokes confirm the cause is retained while an unexpected `RuntimeError`
remains systemic and the retry title is not falsely marked failed. These
smokes, Stage12 bulk/reconciliation/rollout, ASR source/temp policy, Stage11
controller, compile, and `git diff --check` passed. ASR audio and Stage11
deployment/live-adapter smokes could not run in this checkout because the
available Python environments lack `numpy`.

At this handoff update, no RUNNING recovery or retry has been performed.
Publication/Jellyfin writes and Remote ASR/Stage11 re-execution remain
unperformed. The only supported recovery API found in source is
`Stage12RolloutStateStore.recover_running(dvd_id)`, which transitions
`RUNNING -> PENDING` with `CRASH_RECOVERY`; it does not transition to
`FAILED_RETRYABLE`. Do not use it for this requested FAILED_RETRYABLE recovery.
There is no dedicated one-title `RUNNING -> FAILED_RETRYABLE` recovery path;
stop without changing rollout state unless a separately authorized supported
path is established.

## 2026-09-23 Stage12 Jellyfin contract preflight false positive

At source HEAD `8b6848d8913190a540fe4f14e9a2adfd228ffd7e`, an authorized
NHDTC-250 explicit retry command stopped in read-only preflight with
`Jellyfin recognition/fallback contract changed` and `LIVE_EXECUTED=NO`.
No rollout event/state, Remote ASR, Stage11, publication, or Jellyfin write
occurred. NHDTC-250 remains `FAILED_RETRYABLE`, sequence 3, reason
`STAGE12_TITLE_FAILURE`; rollout counts remain `PUBLISHED=158`,
`FAILED_RETRYABLE=14`, `UNRESOLVED=1`, with no active IDs.

Root cause: `contract_check()` in `teddy_discovery_stage12_bulk_runner.py`
required the `PlaybackInfo` request literal to appear in
`recognize_jellyfin_external_subtitle()`. Commit `d18dd5e` factored the exact
GET-only item/playback probe into `_jellyfin_external_subtitle_probe()` but
left that source-location predicate unchanged. The preflight therefore
reported a stale source-structure check, not a changed Jellyfin runtime
contract: the required PlaybackInfo route and exact path/language/external/
SubRip stream checks remain in the helper. Default item refresh, FullRefresh
fallback, the 42-attempt post-FullRefresh polling bound, and publication
reconciliation behavior are unchanged.

The generic fix keeps one shared `contract_check()` for PENDING and explicit
retry paths and checks the PlaybackInfo route in the helper that owns it.
Retry smoke now proves both the current contract passes and removal/mutation
of the helper route fails closed. Read-only explicit-retry and PENDING
preflight functions passed with the local dirty-worktree check isolated for
source-diff smoke; both reported `LIVE_EXECUTED=NO` and zero writes. Stage12
retry, batch, bulk-runner, reconciliation, rollout smokes, compile, and
`git diff --check` passed. The production retry remains unexecuted; perform it
only after reviewing this fix and authorizing a fresh single-title canary.

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
  /opt/stage11-stt-venv/bin/python /opt/missav-pwa-subtitle-stage11/teddy_discovery_stage12_bulk_runner.py \
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

## Stage13-B read-only Library backend — 2026-09-28

Implemented a GET-only `/api/library` read model and runtime installation for
the Stage13 File Manager. The list is sourced from current `jav` holdings with
`present=1`; Stage12 rollout rows are read-only optional state. Detail and
playback resolve a canonical DVD-ID through the current holding before using
its canonical media identity. No delete route or new player was added.

`GET /api/library` supports case-insensitive DVD-ID/title search, KO
`present`/`absent`, unresolved and mismatch filters, and the requested six
sort keys. `GET /api/library/<dvd_id>` validates the canonical ID.
`GET /api/library/<dvd_id>/stream` reuses `teddy_storage`'s existing SSH
Range response implementation with the fixed JAV root; clients cannot submit
a path. API errors use the existing JSON `status/error.code/message` shape.

Managed size reads only DB-derived canonical title folders over the existing
dedicated NAS SSH identity and known-host boundary. One bounded inventory
request covers the holdings in a list call (maximum 250 holdings, 512 entries
per title, depth 5, 30,000 entries overall, 16 MiB canonical subtitle payload,
64 MiB response). Symlinks, unexpected entry types, limits and transport
failures produce an unknown total with a reason code. The summary reports the
sum of known item bytes plus completeness and unknown count.

KO status reuses Stage12's `_classify_subtitles`, canonical sidecar candidate
selection and SRT parser using bounded NAS inventory/read data. Stage12
terminal state and reason are an optional left join; Stage12 `UNRESOLVED`
stays distinct from ordinary absence. Jellyfin uses one GET-only path inventory
request bounded to 10,000 items; exact path matches are recognized, complete
inventory misses are absent, and incomplete/failed requests are unknown.

NAS added date never uses media filesystem timestamps. A matching
`COMPLETED` organizer job must target the exact canonical media relative path;
its creation and completion timestamps must resolve to the same KST date.
That date is labeled `ORGANIZER_COMPLETION_BOUNDED_DATE` with
`nas_added_at=null`; otherwise the value remains unknown. This is a bounded
date claim, not an exact placement instant.

The app container receives the rollout DB, NAS dedicated key/known_hosts and
Jellyfin API key through read-only mounts. It does not mount the JAV library
locally. A read-only API source smoke against the production Discovery and
rollout databases returned 177 current holdings independently of the 173
rollout rows and retained EBWH-296, MIAD-866, MIRD-258 and SKMJ-774. The
production database files were mounted read-only for this smoke. No production
database/NAS/Jellyfin write, NAS/Jellyfin request, refresh, Hermes or VM122 call
occurred.

The fixture smoke covers holdings absent from rollout, normalized subtitle
states, KST same-date/cross-date behavior, no mtime fallback, bounded size and
failure states, searches, filters, every sort mode, invalid requests,
canonical playback identity/path traversal rejection, Jellyfin recognized /
absent / unknown behavior, runtime route installation, auth guard, and
byte-for-byte unchanged fixture databases. The full Docker image build and the
Stage12 inventory, Jellyfin, Downloader API and existing stream-range smokes
passed. `python -m py_compile` and `git diff --check` passed. Next checkpoint:
Stage13-C File Manager UI.

## Stage13-C File Manager UI — 2026-09-28

Added a separate `영상 라이브러리` SPA tab backed by the GET-only Stage13-B
`/api/library` list response. The existing Files page remains intact. The new
page renders the current holdings summary, server-side DVD-ID/title search,
KO/unresolved/mismatch filters and Library API sort modes. Expandable rows
reuse Discovery row/detail styles and show cover, identity, metadata, managed
relative path, subtitle/Stage12/Jellyfin states, NAS date provenance and
bounded size status. Unknown date/size and incomplete library totals remain
explicitly unknown; no browser-side timestamp or size fallback is used.

Playback uses the existing video modal and `<video>` element through the
canonical DVD-ID `/api/library/<dvd_id>/stream` adapter. Existing Files
preview continues through the same shared modal. Covers use the existing
Discovery cover route. No delete control or request was added. The UI has no
per-item detail fetch and makes no per-item playback/Jellyfin requests.

Validation passed: new File Manager UI shell smoke, existing Discovery UI
shell smoke, subtitle status UI smoke, Stage13-B fixture Library API smoke in
the Docker image, Python compile, `git diff --check`, and a full Docker image
build. Responsive CSS breakpoints were checked by the UI shell smoke; no
browser rendering harness is installed in the local environment. This is a
source-only checkpoint: no production deployment/restart, database/NAS write,
Jellyfin write/refresh, or delete request was performed. Next checkpoint:
Stage13-C production deployment preflight and read-only canary.

## Stage13-C production deployment attempt and rollback — 2026-09-28

Preflight began from clean source HEAD
`853930c05b92ec03363199eafbada1099cf033da` on
`teddy-subtitle-stage11`; the exact GitHub branch matched. Production Compose
was `/opt/missav-dlp-web/compose.yaml` with its existing
`/opt/missav-dlp-web/gluetun.env`. Candidate rendering kept all four service
definitions, unrelated services, Downloader port 58000, network, restart
policy and existing storage mounts unchanged. The app retained its
read-only dedicated NAS key/known_hosts and rollout DB mounts, gained the
existing Jellyfin API key as a read-only file mount, and received the
`TEDDY_NAS_*`, `TEDDY_JELLYFIN_*` and `TEDDY_STAGE12_ROLLOUT_DB` environment
names required by Stage13 runtime. No local JAV mount was added. Only the
Downloader web service was recreated; Gluetun and browser services were not
restarted.

The exact source built successfully as image
`sha256:5b7aa9cdbe3344f541ff321ea30925aede10beda69127385409c04a510d75247`,
tagged `ghcr.io/ssikgun/missav-dlp-web:stage13c-853930c05b92` and labeled with
the source revision. Library API and static UI assets were present. External
unauthenticated checks retained `/` redirect and API 401 behavior; Library
JS/CSS returned 200.

The production read-only canary reported 177 present holdings independently
of the 173 Stage12 rows, including EBWH-296, MIAD-866, MIRD-258 and SKMJ-774.
Counts were KO `VALID=163`, `UNRESOLVED=10`, `ABSENT=4`, mismatch 0. Known
managed size summed to 509,297,211,868 bytes with `size_complete=true` and
zero unknown items. Two historical bounded dates had
`nas_added_at=null` and `ORGANIZER_COMPLETION_BOUNDED_DATE`; the unknown-date
sample remained null/`UNKNOWN`. Two positive managed-folder sizes were
confirmed. Jellyfin returned 177 exact recognized paths. DVD-ID/title search,
KO present/absent and unresolved filters, plus NAS date/DVD-ID/size sorts
passed. A canonical playback adapter request returned HTTP 206 for bytes
0–2047 (2,048 bytes); no full media was read or saved. These requests used
bounded exact DB-derived title paths and one bounded Jellyfin GET inventory.

Canary failure: Stage12 rollout rows for HMN-899 and NHDTC-250 contained
distinct terminal reasons `STAGE12_UNSAFE_AUDIO_TIMELINE` and
`STAGE12_BASELINE_ASR_NO_SPEECH`, but the Library API selected the generic
`inventory_reason=NO_CANONICAL_KO_SRT` first and returned
`STAGE12_UNRESOLVED` / `자막 상태 확인 필요` for both. JUR-750 correctly
returned `SUBTITLE_INVENTORY_INVALID` / `기존 자막 상태 확인 필요`. The
distinct Stage12 reason mapping therefore did not meet the production canary
contract. This source defect must be fixed and fixture-tested before another
deployment attempt. No subtitle body or raw artifact was emitted.

The web app alone was rolled back to the captured prior image
`sha256:fb1e9c6dc655c3cd7044e8a8c1711414589e2c1695503e866fe178c3396e6b79`.
It is running with the original compose configuration; the NAS key remains
read-only and no Jellyfin key mount or Stage13 aliases remain. Other services
remained running. A browser binary exists in the separate browser container,
but no authenticated rendering session/harness was available; visual viewport
verification remains pending manual review. The deployed Stage13 image did
not pass canary and is not the active production image.

Production write audit for this attempt: Discovery/rollout DB writes 0, NAS
writes/deletes 0, Jellyfin writes/refreshes 0, Hermes calls 0, VM122 calls 0,
subtitle generation 0, permanent deletes 0. Only the Downloader app container
was deployed and rolled back. Next: correct terminal-reason precedence or
normalization, run the fixture smoke and exact-source deployment preflight
again, then repeat the read-only canary.

## Stage13-C1 unresolved reason resolver hotfix — 2026-09-28

Updated the Library `_reason()` resolver to inspect
`last_transition_reason` and `inventory_reason` independently, using the
existing `UNRESOLVED_LABELS` concrete reason list. A specific transition
reason now wins when present; otherwise a specific inventory reason remains
authoritative. Only when neither field contains a known concrete reason does
an unresolved terminal state use `STAGE12_UNRESOLVED` / `자막 상태 확인 필요`.
The inventory-only helper call path remains supported. No per-title behavior
or DVD-ID mapping was added.

Fixture cases passed for unsafe audio timeline, baseline ASR no speech,
inventory-invalid-only, generic unresolved, and inventory-only helper
compatibility. The complete Stage13-B fixture Library API smoke, Stage13-C
Library UI shell smoke, Stage12 holdings inventory smoke, Python compile and
`git diff --check` passed. These tests used fixtures only. Production was not
deployed or restarted; DB/NAS/Jellyfin writes, Hermes/VM122 calls, subtitle
generation, and delete operations were all zero. Production remains on the
previous known image after the Stage13-C1 source fix. Next: build and deploy
the corrected source candidate, then rerun the Stage13-C production
read-only canary.

## Stage13-C2 hotfix production redeploy and canary — 2026-09-28

Built exact source HEAD `044be13a507b20bb1040eb432cb16cb8deb22233` as
`ghcr.io/ssikgun/missav-dlp-web:stage13c2-044be13a507b` with image ID
`sha256:2ac1125af07b5f55e78daa85030a9e32c793e44eb1182a3cff0fe58e34a48566`.
The source revision label and Library API/UI assets were verified. Using the
production Compose file and env source, only `missav-dlp-web` was recreated;
the original port, network, storage mounts and read-only NAS/rollout/Jellyfin
secret boundaries were retained. Gluetun and browser service container IDs
were unchanged. The new image is running with restart count 0. No rollback was
performed.

The production read-only Library list canary passed with 177 current
holdings, `VALID=163`, `UNRESOLVED=10`, `ABSENT=4`, and mismatch 0. It retained
EBWH-296, MIAD-866, MIRD-258 and SKMJ-774. Exact reason results were:
HMN-899 `STAGE12_UNSAFE_AUDIO_TIMELINE` / `오디오 타임라인 이상`, NHDTC-250
`STAGE12_BASELINE_ASR_NO_SPEECH` / `음성 대사 없음`, and JUR-750
`SUBTITLE_INVENTORY_INVALID` / `기존 자막 상태 확인 필요`. None returned the
generic fallback. This closes the Stage13-C1 production reason blocker.

Bounded representative NAS/Jellyfin check for ADN-785 returned positive known
managed size, NAS date `2026-09-01` with `nas_added_at=null` and
`ORGANIZER_COMPLETION_BOUNDED_DATE`, and Jellyfin `RECOGNIZED`. HMN-899 Library
playback returned HTTP 206 for bytes 0–1023 (1,024 bytes); no media body was
saved. The existing Files list helper returned zero remote media entries, so
there was no safe existing Files item on which to run the requested Range
regression. No arbitrary path was tried. The Files playback Range canary
remains unverified until an existing remote Files entry is available.

Library JS/CSS returned HTTP 200. The deployed template has Library, Discovery
and Files tabs, one shared video element/modal, and the Library DVD-ID stream
adapter; no Library delete UI/request exists. Public auth behavior remained
`/` redirect and API 401. A Chrome process exists in the separate browser
container, but there is no authenticated DevTools/render harness; visual
viewport verification is `PENDING_MANUAL`.

No rollback. Production write audit: DB writes 0, NAS writes/deletes 0,
Jellyfin refresh/write 0, Hermes 0, VM122 0, subtitle generation 0, permanent
delete 0. Production remains on image
`sha256:2ac1125af07b5f55e78daa85030a9e32c793e44eb1182a3cff0fe58e34a48566`.
Next: verify existing Files playback when a remote Files media item is
available, then perform authenticated desktop and narrow/mobile viewport
review. The deployed candidate is retained while those checks are pending.

## Stage13-C3 File Management navigation refactor — 2026-09-28

Refactored the frontend navigation without changing Library, subtitle-status,
or Files API contracts. The sidebar now has one folder-icon `파일 관리`
entry, opening the former Library SPA page renamed for users. Its default
subtab is `보유 라이브러리`; `자막 처리 현황` is a sibling subtab. The status
panel was removed from Settings and placed under File Management with a note
that pipeline job counts are separate from holdings. Status labels now use
text-oriented emoji labels instead of traffic-light symbols. `/api/subtitles/status`
loads on status-subtab activation and polls every 10 seconds only while both
the File Management page and status subtab are active.

The existing standalone Files content was moved under Download as the
`정리 전 파일` tab beside default `다운로드 작업`. Existing file control IDs,
`fetchFiles`, search/sort, actions, and `/api/files/.../stream` playback are
retained; opening the subtab invokes `fetchFiles`. The explanatory text notes
that files disappear from this view after organizer movement to the JAV
library. The shared video player remains singular and no permanent Library
delete UI/request was added. Discovery and Settings controls remain present.

Updated the Library, subtitle-status, Discovery shell checks and added
`teddy_file_management_navigation_smoke.py`. Those checks, subtitle status
fixture smoke, Python compile, and `git diff --check` passed. The complete
local Docker image build passed as
`missav-stage13c3-smoke:c87500b` (`sha256:0b2622d358401fc107dab6324ce1d933f145a22933a76e758665525c6a56eaa6`).
Its existing Browser build patcher was updated to anchor on the renamed single
File Management route and current Discovery page position.

This checkpoint did not deploy or restart production. Production app image
remains `sha256:2ac1125af07b5f55e78daa85030a9e32c793e44eb1182a3cff0fe58e34a48566`.
DB/NAS/Jellyfin writes, Jellyfin refreshes, subtitle generation, permanent
delete, Hermes calls and VM122 calls were all zero. Next: deploy the new UI
source separately, then perform authenticated manual desktop and narrow/mobile
visual acceptance.

## Stage13-C4 File Management production redeploy and focused canary — 2026-09-28

Built exact source revision
`6063c51247f1f2dc919fe583557482b225bbdd8c` as
`ghcr.io/ssikgun/missav-dlp-web:stage13c4-6063c51`; image ID is
`sha256:46b71ff6fdbc2a4d764b2fc6d62877c2e82750176b4c98f4e60641eb2d255d38`.
The image revision label matches the full source SHA and Library/navigation
assets were present. Candidate Compose rendering used the production
`compose.yaml`, `gluetun.env`, existing C2 override and an app-image-only
override. App port/network/storage and read-only secret, Discovery DB,
Stage12 DB/runtime and Jellyfin mounts matched the running configuration.
Only `missav-dlp-web` was recreated with `--no-deps`; gluetun and both browser
container IDs did not change. The app is running with restart count 0; no
container healthcheck is configured, and `/login` returned HTTP 200.

Deployed image static/runtime checks confirmed exactly one File Management
sidebar entry, no standalone Files or Video Library entry, and retained
Download, Discovery, Browser and Settings entries. File Management has the
`보유 라이브러리` default tab and `자막 처리 현황`; Download has
`다운로드 작업` default and `정리 전 파일`. Settings retains its config
controls and no subtitle status panel. The status API path, active-page plus
active-subtab polling guard, 10-second interval, semantic status labels,
single shared video element, separate Library and Files stream wiring, and
absence of Library delete UI/request were confirmed from the deployed image.

The production read-only Library model returned 177 current holdings,
`VALID=163`, `UNRESOLVED=10`, `ABSENT=4`, mismatch 0; all four holdings without
Stage12 rows remained present. Known managed size totaled 509,297,211,868
bytes with complete=true and zero unknown items. HMN-899, NHDTC-250 and
JUR-750 retained their concrete expected reason codes and Korean labels.
Bounded representative NAS sizes were positive, ADN-785 had date
`2026-09-01` with `nas_added_at=null` and
`ORGANIZER_COMPLETION_BOUNDED_DATE`, and representative Jellyfin GET matches
were `RECOGNIZED`. The subtitle status read-only snapshot was `idle`, with
163 PUBLISHED, 10 UNRESOLVED, no active DVD-ID, and the existing heartbeat
marked stale; last activity was retained by the status source.

The canonical ADN-785 stream mapping passed to the existing Range helper and
returned 206 for bytes 0–1023 (1,024 bytes); the body was not saved. This was
an internal helper canary, not an authenticated HTTP route request. The
existing Files metadata helper reported zero current entries, so
`TRANSIENT_FILES_RANGE_CANARY=N/A_NO_CURRENT_FILE`. The old Files API,
`fetchFiles`, search/sort, action and stream wiring remain in the deployed
image. Unauthenticated `/` retained its login redirect, `/api/library`
returned 401, and Library JS/CSS plus subtitle JS returned HTTP 200. No
authenticated HTTP or DevTools browser harness was available, so the
authenticated API route/interactive subtab lifecycle and desktop/mobile
visual viewport remain pending Teddy review; no auth bypass was used.

The new image remains deployed; no rollback was performed. Production write
audit: DB writes 0, NAS writes/deletes 0, Jellyfin refresh/write 0, Hermes 0,
VM122 0, subtitle generation 0, permanent Library delete 0. Only the web app
image/container was replaced. Next: Teddy performs authenticated desktop and
narrow/mobile review, including the subtab interactions and playback button.

## Stage13-C5 subtitle status dark-theme CSS hotfix — 2026-09-28

Added scoped `html[data-theme="dark"]` overrides to
`templates/teddy-subtitle-status.css`. The panel now uses the existing
`#111827` dark surface and `#273449` border; metric cards and badges use the
existing `#1f2937` secondary surface with readable foregrounds. Title,
current status, metric values/labels and footer use the established dark
theme text palette. Every badge state, including idle, running, attention,
stale, error and unavailable, remains legible with neutral styling; emoji and
text continue to carry the state meaning. Existing light-theme base values
and the 680px two-column metric layout were left unchanged.

Extended `teddy_subtitle_status_ui_smoke.py` to check dark selectors and
foreground/background declarations, preserve the light base declarations,
and retain the narrow grid. Subtitle status UI, File Management navigation,
Library UI, Discovery UI shell, Python compile and `git diff --check` passed.
The full local Docker image build `missav-stage13c5-smoke:9692b06` passed,
including all configured UI smoke checks.

No production deploy or restart was performed. Production remains on the C4
candidate image `sha256:46b71ff6fdbc2a4d764b2fc6d62877c2e82750176b4c98f4e60641eb2d255d38`.
DB/NAS/Jellyfin writes, Jellyfin refresh, Hermes/VM122 calls, subtitle
generation and delete operations were all zero. Next: deploy the CSS hotfix
by replacing only the production web app, then Teddy verifies dark-mode status
panel appearance.

## Stage13-C6 subtitle status dark-mode production redeploy — 2026-09-28

Built exact source HEAD `b63bd132bc75753b8b1127cb792e42c4b33e8324` as
`ghcr.io/ssikgun/missav-dlp-web:stage13c6-b63bd13`. The production image ID
is `sha256:7f427ebf957180466c7fe0d56122dd5eddfc833f3919ab9527741d8a1399df19`;
the OCI revision label matches the source HEAD. Before replacement, the
running C4 rollback image was recorded as
`sha256:46b71ff6fdbc2a4d764b2fc6d62877c2e82750176b4c98f4e60641eb2d255d38`.
The production Compose/env and existing overrides were rendered with only
the app image changed. Only `missav-dlp-web` was recreated using
`--no-deps`; gluetun and both browser services kept their prior container
IDs. The new app is running with restart count 0, and `/login` returns 200.

The live-served `teddy-subtitle-status.css` returned 200 and passed checks for
the dark panel selector/surface/border, current text, metric surface/value/
label, footer and badge override. Existing light panel/metric base values and
the 680px two-column layout also passed. Status JS returned 200 and retained
all six semantic status labels. No runtime/status enum, API, or navigation
source changed.

Read-only production holdings source returned 177 rows. The existing status
snapshot builder returned normally (`idle`, 163 PUBLISHED, 10 UNRESOLVED,
heartbeat present); unauthenticated `/api/subtitles/status` and
`/api/library` requests returned the expected 401. No authenticated browser
or DevTools harness was available, so API contents were checked through the
same read-only source builders rather than bypassing auth. Deployed template
checks confirmed File Management/Download navigation, Settings controls,
Discovery, Library playback wiring, a single shared video element, and no
Library delete UI/request. Static Library, Discovery and status assets
returned 200. `VISUAL_DARK_THEME_CANARY=PENDING_TEDDY`.

No rollback. Production write audit: DB writes 0, NAS writes/deletes 0,
Jellyfin refresh/write 0, Hermes 0, VM122 0, subtitle generation 0, Library
delete 0. The current production image remains
`sha256:7f427ebf957180466c7fe0d56122dd5eddfc833f3919ab9527741d8a1399df19`.
Next: Teddy opens `파일 관리 > 자막 처리 현황` with dark theme enabled and
confirms the panel appearance in the real browser.

## Stage13-E1 Permanent Delete DRY-RUN prepare/validate — 2026-09-28

Implemented read-only `POST /api/library/<dvd_id>/delete/prepare` and
`POST /api/library/<dvd_id>/delete/validate`. Both require the existing
authenticated session, JSON request, exact same-origin `Origin`, and the
explicit `X-Teddy-Delete-Intent` header. The request identity accepts only the
canonical DVD-ID; the server re-reads the current present JAV holding and
revalidates its canonical mapping. No arbitrary path or filename is accepted.

Prepare and validate use the existing hardened dedicated `CompletionSSH`
transport and inspect one database-derived title directory only. The
read-only `lstat` manifest rejects unsafe components, root escape, symlinks,
special files, nested directories and entry overflow. Its SHA-256 covers
canonical sorted manifest metadata (relative filename, size, mtime_ns, inode,
device and regular-file type), not media contents. The holding's canonical
media size and mtime_ns must match. Stage12 subtitle state and Jellyfin state
are read-only summary fields; no subtitle content is returned.

Prepare tokens are cryptographically random, process-memory only, DVD-ID / manifest /
holding-identity bound, five-minute TTL and bounded to 128 entries. Validation
re-reads the holding and exact manifest. Drift fails closed as
`MANIFEST_CHANGED`; identical successful replay returns the same validation
result. The Library detail UI requires both the explicit acknowledgement and
an exact typed DVD-ID, displays the safe manifest summary, and stores the token
only in memory. Closing the dialog clears it. Successful validation displays
`삭제 준비 검증 완료 · 실제 삭제는 아직 비활성`; no commit endpoint exists.

Added a non-persistent safe future provenance dataclass/serializer contract
(`schema_version`, DVD-ID, manifest SHA, counts/bytes, phase, source identity
fingerprint, timestamps and result). Fixture smoke covers valid and invalid
identity, duplicate/missing holdings, path traversal, root/family/title and
child symlinks, special files, nested directory, entry bound, missing/drifted
canonical media, stable order/hash, token binding/expiry/replay, missing
acknowledgement, subtitle/Jellyfin read-only states, query-only DB bytes, and
the absence of a deletion primitive. Existing Library API, Library UI,
File Management navigation, subtitle status, and Discovery smokes passed.
Python compile and `git diff --check` passed; full Docker build
`missav-stage13e1-smoke:874d3aa` passed.

Stage13-C remains CLOSED / PASS. This E1 checkpoint did not deploy. No real
production title was prepared. Actual delete calls = 0; DB writes = 0; NAS
writes/deletes = 0; Jellyfin writes/refresh = 0; Discovery reconcile writes =
0; Hermes/VM122 calls = 0; subtitle generation = 0. Next: Stage13-E2 may deploy
the DRY-RUN endpoints for a read-only canary; actual deletion remains disabled.

## Stage13-E2 Permanent Delete DRY-RUN production deployment — 2026-09-28

Built and deployed exact source HEAD `ebd04178991659661efd416d0435e03e0ddc5584`
as `ghcr.io/ssikgun/missav-dlp-web:stage13e2-ebd0417`, image
`sha256:62c276b041a42a20a81fbbe925ff165f0b49a0674dff898fd5e2855f60afadef`.
The previous running app image was
`sha256:7f427ebf957180466c7fe0d56122dd5eddfc833f3919ab9527741d8a1399df19`.
Production Compose was rendered with the existing env and C2/C4/C6 overrides;
only the app image differed. Only `missav-dlp-web` was recreated. The app is
running with restart count 0; other service container IDs were unchanged.
Unauthenticated `/` still redirects to login and Library/status/prepare/
validate API requests remain 401. No credential or auth bypass was used.

The current read-only Discovery source was 182 present JAV holdings before
deployment and remained 182 afterward (182 distinct IDs, all `MATCHED`, no
duplicate IDs), rather than the E2 expected 177. This is recorded as a
pre-existing count discrepancy; no cause or timing is inferred. ADN-785 was
rechecked as one valid present canonical holding with no active subtitle job.
Using the deployed bounded manifest reader against only its exact canonical
title directory found 4 direct regular files totaling 3,528,183,972 bytes;
manifest identity SHA prefix `646a207fa39f`. The canonical media size/mtime
matched the holding. No symlink, special file, nested directory or entry
bound violation was found. Read-only state was KO `VALID` and Jellyfin
`RECOGNIZED`. This was an internal exact-folder reader canary, not a call to
the authenticated prepare API; no token was issued.

The production prepare/validate/replay HTTP canary was not run because no
existing authenticated same-origin HTTP/browser session was available. The
unauthenticated guard was verified, including form-style prepare rejection;
authentication was not bypassed. Therefore API prepare summary, `READY_FOR_COMMIT`,
and replay idempotency remain unverified in production. Source/runtime route
inspection confirms only prepare and validate routes are registered; there is
no delete commit endpoint. Deployed UI wiring contains prepare/validate only,
and no commit button. Fixture smoke remains the evidence for token expiry,
wrong identity, missing acknowledgement, drift and replay paths.

Deployed template/static checks passed for the Library page, prepare/validate
UI wiring, existing Library and transient Files stream adapters, and exactly
one shared video element. No authenticated browser harness is installed, so
`DELETE_DRYRUN_UI_VISUAL=PENDING_TEDDY`.

No rollback was performed. The E2 candidate remains deployed. Production write
audit: DB writes 0, NAS writes/deletes 0, Jellyfin write/refresh 0, Discovery
reconcile writes 0, Hermes 0, VM122 0, subtitle generation 0, permanent delete
0. The only production mutation was replacement of the web app image/container.
E2 is incomplete pending an authenticated same-origin prepare/validate/replay
canary and reconciliation of the observed 182-versus-177 holdings count before
claiming the requested production contract. Actual deletion remains disabled.

## Stage13-E2C delete prepare 403 diagnostics hotfix — 2026-09-29

Added bounded one-line diagnostics to the authenticated Library delete-intent
guard. Rejections now log the exact `invalid_request_boundary` or
`invalid_request_origin` code and a bounded subreason (`mimetype`,
`intent_header`, `origin_missing`, `scheme_mismatch`, `host_mismatch`, or
`cross_site`), with sanitized request/origin scheme and host, forwarded-header
presence/value, `Sec-Fetch-Site`, content type, method, intent and header value.
Cookie, session, authorization, token, body, query and client IP are not logged.
All authentication, JSON, intent, same-origin and `Sec-Fetch-Site` checks are
unchanged; no forwarded header is trusted by this change.

The Library UI now displays only allowlisted safe server error codes for
prepare and validate failures; unknown codes and raw server messages continue
to use the generic UI text. Prepare/validate success behavior and the disabled
actual-delete state remain unchanged.

Fixture smoke exercised invalid content type, wrong intent, missing Origin,
scheme mismatch, host mismatch, cross-site, and valid same-origin requests.
It checked exact subreason logs and verified cookie/session/token sentinel
values were absent. Library API/UI, delete DRY-RUN, File Management
navigation, subtitle status, Discovery UI, Python compilation and
`git diff --check` passed. Full Docker build passed from the isolated source
commit `22bb71edddf638e59f98eb4c945e31f204d47100`, excluding unrelated local
subtitle parser changes.

Deployed `ghcr.io/ssikgun/missav-dlp-web:stage13e2c-22bb71e`, image
`sha256:ab0a8281d6ecb7b81fa5851cd5e523059b44de74e3270a79cfd9c9a2e07d63dc`.
Only `missav-dlp-web` was recreated; the prior E2 image was retained as
rollback candidate. The app is running with restart count 0. `/login` returned
200, unauthenticated `/` redirected to login, Library and subtitle APIs
returned 401, and Library JS/CSS returned 200. No authenticated prepare was
retried by Codex. Token issue = 0 and actual delete = 0; no validate request,
Discovery reconcile, Jellyfin refresh, Hermes/VM122 call or subtitle generation
was invoked by this checkpoint.

Next: Teddy clicks `ADN-785 > 🗑️ 영구 삭제` once in the authenticated browser.
The safe UI code and application log should now identify the rejected guard
branch. Actual deletion remains disabled.

## Stage13-E2E trusted public-origin helper — 2026-09-29

Added a strict shared parser in `teddy_public_origin.py` and configured
`TEDDY_PUBLIC_ORIGIN` as the required app environment value in the canonical
production Compose file. The parser accepts only HTTP(S) origins with a host
and optional valid port; it rejects userinfo, non-root paths, query/fragment,
wildcards, malformed authorities and unsupported schemes. Canonical values
include scheme, normalized hostname/netloc and effective port, so default
ports normalize consistently.

The delete prepare/validate origin guard still requires authentication, JSON,
the exact intent header, a present same-origin Origin, and non-cross-site
`Sec-Fetch-Site`. It now compares the browser Origin to
`TEDDY_PUBLIC_ORIGIN`, and separately verifies the app-visible request Host
against that configured authority. The private `request.scheme` is not part
of the decision, allowing the established HTTPS-public/HTTP-private-proxy
shape. `X-Forwarded-Proto` and `X-Forwarded-Host` remain diagnostic only and
are not trusted. Missing or invalid configuration rejects closed with the
existing `invalid_request_origin` response and bounded diagnostic subreason.
No ProxyFix or domain-specific production source constant was added.

Fixture coverage passed for proxy-terminated HTTPS, scheme/host/port mismatch,
default and explicit port handling, missing/malformed/unsafe configuration,
forwarded-header spoofing invariance, cross-site and intent rejection, plus
successful prepare and validate-only responses. Both phases returned
`actual_delete_performed=false`; no delete/commit endpoint exists. Library
API, Library UI, File Management navigation, subtitle status and Discovery UI
smokes passed. Python compilation and `git diff --check` passed. The full
Docker image build passed as `missav-stage13e2e-smoke:f795bec-final`,
image `sha256:1edd1c4ea95e382bc884ff43d801695ec1ab543dc164e1d9ab33acf88be0f65b`.

No production environment file was changed and no image was deployed or
restarted. Production prepare/validate was not called. Actual delete = 0;
production DB writes = 0, NAS writes/deletes = 0, Jellyfin writes/refresh = 0,
Hermes/VM122 calls = 0, and subtitle generation = 0. Next: Stage13-E2F may
configure `TEDDY_PUBLIC_ORIGIN` in the production environment, redeploy only
the web app, and have Teddy retry the authenticated prepare/validate DRY-RUN.

## Stage13-E2F trusted public origin production deployment — 2026-09-29

The production environment previously had no `TEDDY_PUBLIC_ORIGIN` key.
Added exactly one entry with value
`https://downloader.ssikgun.com`, preserving the env file's existing owner,
mode and LF convention. Added the corresponding environment pass-through to
the production `missav-dlp-web` Compose service. No other env entry or
service configuration changed.

Built source HEAD `6e5fa88ce17ada4f277fcd8d4be8cc8f02cc1b6a` as
`ghcr.io/ssikgun/missav-dlp-web:stage13e2f-6e5fa88`, image
`sha256:9931fa76baff36984e2cef51f3de77c019236f538da1983582a8856188398cdc`.
The image carries OCI revision label
`6e5fa88ce17ada4f277fcd8d4be8cc8f02cc1b6a`. Only the `missav-dlp-web`
service was recreated with `--no-deps`. Its previous image,
`sha256:ab0a8281d6ecb7b81fa5851cd5e523059b44de74e3270a79cfd9c9a2e07d63dc`,
was retained as rollback candidate; rollback was not needed.

The app is running with restart count 0 and published port 58000 unchanged.
Gluetun and both browser container IDs remained unchanged. Compose render
showed the only app changes were the image and public-origin environment;
ports, network, data mounts, read-only Discovery/rollout DBs, NAS SSH
credential mount and Jellyfin key mount stayed unchanged. Runtime env check
matched the exact configured value. The deployed helper parsed it as
`scheme=https`, `host=downloader.ssikgun.com`,
`effective_port=443`, valid=true.

Unauthenticated `/login` returned 200, `/` redirected to login,
`/api/library` and delete prepare returned 401. Library, Discovery and
subtitle status assets returned 200. Runtime route inspection found prepare
and validate only; no delete/commit route is registered. No authenticated
prepare or validate was called and no session was created or copied.

Production writes: DB 0, NAS write/delete 0, Jellyfin write/refresh 0,
Discovery reconcile 0, Hermes 0, VM122 0, subtitle generation 0, permanent
delete 0. The only production mutations were the public-origin env/config
setting and replacement of the web app image/container. Next: Teddy performs
the authenticated ADN-785 prepare and validate-only flow in the browser.
Actual deletion remains disabled.

## Stage13-E2 authenticated production DRY-RUN closure — 2026-09-29

Teddy completed the authenticated production UI DRY-RUN for ADN-785. Prepare
reported 4 managed files totaling approximately 3.3 GB, manifest SHA prefix
`646a207fa39f`, Korean subtitle present and Jellyfin recognized. Validate
returned `READY_FOR_COMMIT`. Actual deletion remained disabled and no
production file was deleted.

Stage13-E2 is CLOSED / PASS for the prepare/validate DRY-RUN contract.
ADN-785 was only the DRY-RUN subject; this outcome does not approve it or any
other title for a future real deletion canary. Stage13-F1 implementation
continues offline with its feature gate disabled and production delete count
remaining zero.

## Stage13-F1 one-title permanent delete implementation — offline PASS, 2026-09-29

Stage13-E2 remains CLOSED / PASS for authenticated prepare/validate DRY-RUN.
Teddy's ADN-785 observation (4 managed files, approximately 3.3 GB,
manifest prefix `646a207fa39f`, KO present, Jellyfin recognized,
`READY_FOR_COMMIT`) did not approve ADN-785 or any other work for actual
deletion.

F1 adds `POST /api/library/<dvd_id>/delete/commit`, plus durable
`/delete/reconcile` and `/delete/resume` recovery paths. Actual mutation is
fail-closed behind `TEDDY_LIBRARY_DELETE_ENABLED`; missing/false disables it.
Commit requires authenticated JSON, the existing destructive intent and
trusted public-origin guard, a validated short-lived DVD-bound token, exact
typed DVD-ID, acknowledgement and the final phrase, then a fresh canonical
holding/source fingerprint and exact manifest match.

The mutator uses the existing hardened dedicated NAS SSH transport and sends
bounded JSON to a fixed Python helper. It lstat-checks the JAV root, family,
title directory and direct entries; permits only exact regular-file entries
matching type, device, inode, size and mtime; unlinks those entries one by
one; and rmdirs only the now-empty exact title directory. It never recurses,
uses a glob, removes a family parent, or uses a CT108 JAV mount. Manifest SHA
identifies canonical manifest metadata, not file contents.

Durable audit/recovery state is SQLite at
`/downloads/teddy-library-delete-provenance.sqlite3`, on the existing
persistent `/downloads` storage. It records operation/DVD identity,
source fingerprint, manifest metadata, timestamps, removed/remaining entry
names, bytes/counts and result/reconciliation states; no token, session,
secret, subtitle body or absolute NAS path is stored. Partial operations can
resume only against the original manifest; post-restart recovery re-inventories
the exact title folder and accepts only the exact expected remaining subset.
After NAS completion, Discovery marks that exact holding `present=0`; then
Jellyfin is reconciled by exact-path GET, targeted item refresh, and GET
verification. Failures remain `RECONCILE_PENDING` without reversing deletion.

The UI requires the existing prepare/validate sequence followed by a separate
exact DVD-ID, acknowledgement, fixed phrase and explicit commit action. The
commit controls remain disabled unless prepare reports the server feature gate
enabled, and the button disables on first click. API replay does not repeat a
completed mutation. Offline fixtures cover gate/auth/origin/token/identity
failures, manifest and filesystem drift, symlink/special/nested rejection,
exact delete boundaries, partial and process-restart recovery, provenance,
Discovery/Jellyfin success and pending recovery, response secrecy and UI
confirmation. Library/API, delete DRY-RUN, File Management, subtitle status,
Discovery and full Docker build checks passed.

Production deploy = NO; production `TEDDY_LIBRARY_DELETE_ENABLED` was not set
or changed. Production DB writes = 0, NAS writes/deletes = 0, Jellyfin
refresh/write = 0, Discovery reconcile writes = 0, Hermes/VM122 = 0,
subtitle generation = 0, actual permanent deletes = 0. Next: Stage13-F2
production deploy/preflight only; keep the gate disabled and do not perform an
actual canary deletion without Teddy's separate explicit approval.

## Stage13-F2A gated production deploy / destructive path preflight — INCOMPLETE, 2026-09-29

Deployed exact source `63fc052e2ad85f75646bdb500640fcb828a561e4` as
`ghcr.io/ssikgun/missav-dlp-web:stage13f2a-63fc052`, image ID
`sha256:e6a5d1f428e3b745a1605017cb89fa09c14a24701fa99f50dfbe26e7abc34b3f`.
Before deploy the rollback image was `sha256:9931fa76baff36984e2cef51f3de77c019236f538da1983582a8856188398cdc`.
Only `missav-dlp-web` was recreated (`--no-deps`); Gluetun and browser
container IDs remained unchanged. The app is running with restart count 0,
port 58000 and its prior network/mount boundary. No rollback was needed.

`TEDDY_LIBRARY_DELETE_ENABLED` is absent from production env, rendered Compose,
and runtime; runtime `delete_enabled` is false. Source order gates commit,
reconcile and resume before provenance creation, holding write or NAS/Jellyfin
mutator calls. Existing F1 offline tests cover `delete_disabled`. No
production authenticated prepare, validate, commit, reconcile or resume was
called. `/login` returned 200, `/` redirected to login, `/api/library` and an
unauthenticated commit returned 401, and Library JS/CSS returned 200.

Provenance uses `/downloads/teddy-library-delete-provenance.sqlite3` (no
production record was created). The path is on persistent host bind
`/opt/missav-dlp-web/work:/downloads`, RW, not tmpfs; its parent exists and
has writable capability. `TEDDY_LIBRARY_DELETE_PROVENANCE_DB` is unset.

Production `TEDDY_DISCOVERY_DB=/discovery/teddy-discovery.sqlite3` maps to
`/opt/missav-dlp-web/discovery/teddy-discovery.sqlite3:ro`. F1 passes this
same `db_path` into `reconcile_discovery_holding()`, which opens it with
SQLite `mode=rw` and conditionally updates exact `holding_id`/DVD/path/
identity from `present=1` to `present=0`. This cannot write through the
current mount: `DISCOVERY_RECONCILE_RW_PATH=BLOCKED_BY_READ_ONLY_MOUNT`.

No existing narrow writer for this exact post-delete lifecycle was found.
Organizer publish updates holdings to `present=1`; Discovery import and the
Stage10 JAV reconcile apply path perform broader inventory reconciliation and
are not suitable request-time single-title writers. The live DB reports
`journal_mode=wal` and has WAL/SHM sidecars. Therefore a second path alias to
the same DB must not be enabled until WAL/SHM coordination is proven: SQLite
sidecar paths are derived from the opened path. Proposed safe follow-up is a
small host-side narrow writer over a local Unix socket, opening the one
canonical DB path and accepting only exact holding identity/fingerprint data;
it performs a parameterized conditional `present=0` update under the shared
writer coordination boundary. The app's existing read DB mount stays RO and
only the delete reconcile caller can use that writer. No helper, RW mount, or
DB write was added in F2A.

The production NAS transport is configured for host `192.168.1.201`, user
`ssikgun`, with key and known_hosts paths under the read-only
`/run/secrets/teddy-nas-transfer` mount. The mutator's library root remains
`/volume1/video/video2/JAV`; F1 uses exact manifest unlink/rmdir, not `rm -rf`,
globs or recursion. No NAS SSH mutation was invoked. Jellyfin reconciliation
uses GET exact-path lookup, targeted API refresh and verification; its API key
mount is RO. No Jellyfin request/write/refresh was performed.

Read-only current holdings snapshot: `storage_root='jav' AND present=1` = 184.
This is a point-in-time count, not a fixed invariant. The provenance path
preflight passed, but safe Discovery reconciliation is a required canary
prerequisite and remains blocked; Stage13-F2A is therefore
`INCOMPLETE — APP_DEPLOYED / DELETE_GATE_DISABLED / DISCOVERY_RECONCILE_BLOCKED`.
Keep this image deployed and gate disabled. Production DB/NAS/Jellyfin writes,
provenance records, subtitle generation, Hermes/VM122 calls and actual deletes
were all 0. Next: implement and fixture-verify the narrow canonical-path
Discovery writer, then separately deploy/preflight it before any real canary.

## Stage13-F2B host-side Discovery reconcile writer — PASS, 2026-09-29

Implemented `teddy_library_discovery_writer.py`: a local Unix-domain socket
server/client with only `health`, `preflight_holding` and `mark_absent` ops.
The newline-delimited UTF-8 JSON frame is capped at 8 KiB, responses at 4 KiB,
unknown fields/operations are rejected, and socket startup refuses a symlink
parent or any pre-existing socket path. The runtime directory contract is
0750 and socket mode 0660; deployment must align the app container's connect
GID with the service group after checking actual runtime identities.

The host service receives the canonical Discovery DB and persistent provenance
DB paths only through administrator-controlled CLI configuration; requests
cannot provide a DB/path/SQL/field value. It reads provenance in SQLite RO /
query-only mode and requires exact operation/DVD/holding/fingerprint identity,
`nas_delete_complete=1`, empty remaining entries, complete exact manifest
removal counts, and a permitted reconciliation state. Discovery writes use
the canonical host DB path, SQLite `mode=rw`, `busy_timeout`, `BEGIN IMMEDIATE`
and one conditional `holdings.present=1 -> 0` update matching holding ID,
DVD-ID, canonical relative path, storage root, parse status, size and mtime.
No WAL mode change or second DB alias is introduced. Same-operation replay is
idempotent when its durable provenance marks Discovery reconciled; another
operation cannot claim an already-absent row.

The web app now defaults to `TEDDY_LIBRARY_DELETE_DISCOVERY_WRITER_SOCKET` and
has no direct RW fallback. Commit and partial-resume paths must receive
`READY` from `preflight_holding` before provenance enters `COMMITTING` and
before the NAS mutator can run. The existing injected direct reconciler remains
available only to offline fixtures. A full fixture exercised socket preflight,
exact fixture deletion, exact holding reconciliation and Jellyfin fixture
completion; unavailable-writer preflight left the NAS fixture untouched and
created no provenance record. Writer protocol, malformed/oversized requests,
identity/provenance failures, conditional update, unrelated-row preservation,
DB-busy behavior, socket permissions, restart replay and no-path/no-token
responses passed. Existing F1 partial/retry, E1 prepare/validate, Library API
and UI, File Management, subtitle status and Discovery smokes passed; Python
compile, `git diff --check` and the full Docker image build passed.

No writer service/socket was installed or created on production. The existing
systemd deployment convention was inspected; F2C must first settle the host
service code install path and service user/group against the web container's
actual UID/GID, then install the unit/runtime directory and bind the socket
directory into only the web app as connect-only/read-only. Configure
`TEDDY_LIBRARY_DELETE_DISCOVERY_WRITER_SOCKET=/run/teddy-library-discovery-writer/writer.sock`;
keep `/discovery/teddy-discovery.sqlite3:ro` and feature gate disabled. The
host writer CLI requires explicit `--discovery-db`, `--provenance-db`, and
`--socket` arguments. No production deploy, service install, feature-gate
change, provenance record, DB write, NAS write/delete, Jellyfin refresh/write,
subtitle generation, Hermes/VM122 call or actual delete occurred. Next:
Stage13-F2C production writer install/socket bind and disabled-gate preflight
only; no one-title deletion.

## Stage13-F2C host-side Discovery writer install and disabled-gate preflight — PASS, 2026-09-29

Exact source `09a3a89bac6af910ca3543f8c076bb0f54e2cb41` was exported to the
immutable host release directory
`/opt/missav-dlp-web/teddy-library-discovery-writer/releases/09a3a89bac6af910ca3543f8c076bb0f54e2cb41/`.
The snapshot contains only the writer and its import dependencies, is
root-owned/read-only, and includes a `SOURCE_COMMIT` marker matching the
expected revision. Host Python is `/usr/bin/python3` (3.13.5); import passed.

The host Discovery directory and DB/WAL/SHM are root-owned mode 0700/0600;
web app also runs as UID 0. A non-root writer cannot safely access them without
changing existing ownership/modes, so F2C retained root and applied a dedicated
primary group `teddy-library-discovery-writer` (GID 988) for the socket. The
systemd unit is `teddy-library-discovery-writer.service`, active/enabled,
`NRestarts=0`, running as root:that group. Sandbox has `NoNewPrivileges`,
`PrivateTmp`, `ProtectSystem=strict`, only the Discovery directory writable,
the provenance work directory read-only, `RestrictAddressFamilies=AF_UNIX`,
and an empty capability set. RuntimeDirectory is systemd-managed at
`/run/teddy-library-discovery-writer`, mode 0750; socket is root:group mode
0660. Controlled restart removed/recreated the runtime socket, changed the
service PID, and host health returned `READY` before and after restart.

Production Compose now passes the socket path, adds supplementary GID 988 to
only the web app, and bind-mounts the socket directory read-only at the same
container path. Rendered config retains port 58000, default network, existing
storage mounts, and `/discovery/teddy-discovery.sqlite3:ro`. The running web
container confirms the socket and Discovery mounts are both read-only and its
supplementary group includes 988; container-side Unix socket health returned
`READY`, proving connect works over the read-only bind. Only
`missav-dlp-web` was recreated; Gluetun and both browser container IDs stayed
unchanged.

Exact F2B image built and deployed: source
`09a3a89bac6af910ca3543f8c076bb0f54e2cb41`, tag
`stage13f2c-09a3a89`, image ID
`sha256:40d68b117add00b0dfa85748780d49c3578e670af42d11aa2ae9dfda805dc787`.
App is running, restart count 0. `/login` and Library JS/CSS returned 200,
unauthenticated `/` redirects to login and `/api/library` returns 401.
`TEDDY_LIBRARY_DELETE_ENABLED` remains missing/disabled in Compose and runtime.

Read-only exact holding probe used ADN-785 / holding 141, canonical MATCHED
identity and its source fingerprint. Container-side `preflight_holding`
returned `READY`; the writer performed `BEGIN IMMEDIATE`, exact SELECT and
ROLLBACK. Before/after current `jav AND present=1` count remained 184 and the
target row identity remained unchanged. No provenance DB/file existed before
the probe and none was created. Its parent `/opt/missav-dlp-web/work` is
root-owned 0755; a future container-created root:root 0600 provenance DB is
readable by the root writer, while systemd exposes the work path read-only.

No `mark_absent`, authenticated commit, reconcile or resume call was issued.
Discovery content writes = 0, provenance record writes = 0, NAS writes/deletes
= 0, Jellyfin refresh/write = 0, subtitle generation = 0, Hermes/VM122 = 0,
actual permanent deletes = 0. Next: Stage13-F2D final pre-canary safety
preflight only; keep the delete gate disabled and do not delete a title.

## Stage13-F2D final permanent-delete safety preflight — INCOMPLETE, 2026-09-29

Source preflight started at `06a75d42ca350e069d7a87b3a45e52241923c91a` on
`teddy-subtitle-stage11`, clean and equal to the server branch. No source code
divergence was found. The running web app remains F2C image
`sha256:40d68b117add00b0dfa85748780d49c3578e670af42d11aa2ae9dfda805dc787`,
running with restart count 0; no service was recreated.

F2C socket wiring had been applied to the production compose but was absent
from the repository deployment compose. Both
`docker-compose.gluetun.yml` and `/opt/missav-dlp-web/compose.yaml` now define
`TEDDY_LIBRARY_DELETE_DISCOVERY_WRITER_SOCKET=/run/teddy-library-discovery-writer/writer.sock`,
the host-to-container runtime directory bind as read-only, supplementary
writer GID 988, and `TEDDY_LIBRARY_DELETE_ENABLED=${TEDDY_LIBRARY_DELETE_ENABLED:-false}`.
Sanitized renders of both compose files agree: gate `false`, public origin
`https://downloader.ssikgun.com`, Discovery DB mounted `:ro`, writer socket
directory mounted `:ro`. The currently running container still has the gate
variable missing; application evaluation is fail-closed (`false`). Its
effective state was not enabled. No compose up/recreate was run.

Writer release remains the immutable
`/opt/missav-dlp-web/teddy-library-discovery-writer/releases/09a3a89bac6af910ca3543f8c076bb0f54e2cb41/`,
service `teddy-library-discovery-writer.service` active/enabled, root-owned
with the restricted `teddy-library-discovery-writer` socket group, PID
978934, no restart loop. Socket is a Unix socket, root:group mode 0660;
runtime directory is 0750. Existing F2C controlled restart evidence remains
valid. Host and container `health` returned `READY`. The exact read-only
probe of ADN-785 / holding 141 returned `READY`; `present=1` and current
holdings count remained 184. This connectivity probe is not canary approval.

Current Discovery snapshot: 184 present JAV holdings, 184 unique DVD-IDs,
0 duplicates and 0 canonical/parse mismatches. Organizer job rows currently
all report `COMPLETED` (184); Stage12 `RUNNING`/`GENERATED` rows currently
number 0. These point-in-time counts do not replace a per-title guard.
Source review found no commit/resume guard that checks the requested DVD-ID
against active organizer/completion work and active subtitle generation.
Therefore `CANARY_BLOCKER=ACTIVE_JOB_GUARD_MISSING` and
`CANARY_READY=NO`; do not enable the gate or perform a canary until a
source fix adds the target-specific fail-closed collision check.

Static ordering review confirms the configured gate and validated token are
checked before mutation; exact current identity/manifest and Discovery writer
`preflight_holding` precede durable `COMMITTING` provenance and the NAS
mutator, including partial/uncertain resume. Production reconciliation uses
the socket writer only; direct SQLite reconciliation is available only when
explicitly injected by offline fixtures, with no production RW fallback.
The writer independently reads durable provenance before its exact conditional
`present=1 -> 0` update. The NAS mutator uses exact manifest `lstat` checks,
per-file `unlink`, then removes only the verified empty title directory; it
does not use recursive delete, globs or arbitrary paths. Partial recovery is
durable and scopes retries to the original manifest/remaining entries.
Jellyfin reconciliation uses API GET by exact path and targeted item refresh
after Discovery succeeds; it does not edit the Jellyfin database, and failure
leaves reconciliation pending rather than reversing NAS deletion.

Offline Discovery writer and F1 delete/recovery fixture smokes passed. No
production prepare/validate/commit/resume/reconcile request was made.
Discovery writes = 0, provenance writes = 0, NAS writes/deletes = 0,
Jellyfin refresh/write = 0, subtitle generation = 0, Hermes/VM122 calls = 0,
actual permanent deletes = 0. Production web image remains unchanged.
Next: implement and fixture-test the per-DVD active-job collision guard,
then repeat F2D preflight before Teddy selects a canary title.

## Stage13-F2E target activity guard — INCOMPLETE FOR CANARY, 2026-09-29

F2D identified `ACTIVE_JOB_GUARD_MISSING`. This checkpoint adds a generic,
read-only target activity guard in `teddy_library_delete_activity.py`; no
production deploy or restart was performed. The F2C production app remains on
its prior image with `TEDDY_LIBRARY_DELETE_ENABLED` missing/effectively false.
Actual delete remains disabled.

Organizer source evidence: `organizer_jobs` has no schema CHECK constraint;
`organizer_apply` creates `RUNNING`, records `PUBLISHED` after publishing the
holding and before source cleanup, then records `COMPLETED`. Failed operations
record `FAILED`; known incomplete recovery states include `CLEANUP_PENDING`
and `DB_FAILED_AFTER_PUBLISH`. The guard treats `RUNNING` and `PUBLISHED` as
active, `COMPLETED` and `FAILED` as terminal, and incomplete/unknown values as
`ACTIVITY_STATE_UNAVAILABLE` (fail-closed). Queries are exact `WHERE dvd_id=?`
against the read-only Discovery DB.

Subtitle source reuses `teddy_subtitle_status.py` active statuses and heartbeat
parser/freshness contract. A target rollout row in `RUNNING` or `GENERATED`
blocks even if heartbeat is stale. A fresh `RUNNING` heartbeat blocks only
when `current_dvd_id` matches the target; a fresh heartbeat naming another
DVD-ID does not. A stale valid heartbeat alone does not block. Missing
heartbeat is allowed when durable state is readable; unreadable/malformed
heartbeat, invalid fresh state, or rollout DB failure returns
`ACTIVITY_STATE_UNAVAILABLE`. Future subtitle controllers can be added as
providers without changing delete-route logic.

Commit performs target checks after final holding/manifest validation and
again after writer preflight, before provenance `COMMITTING` and NAS mutation.
Partial commit retry and incomplete resume use the same two checks before
resuming provenance/mutator work. `RECONCILE_PENDING` recovery remains outside
the activity guard so completed NAS deletion can reconcile. Safe API outcomes
are `delete_target_active` and `delete_activity_unavailable`; no job/session
or heartbeat details are returned. Fixture checks confirmed active/unavailable
before the first check or between checks causes zero NAS mutator calls and no
new provenance operation; idle controls continue through the existing fixture
path; active partial resume is blocked; already-completed reconciliation is
not blocked.

`SHARED_PER_TITLE_LOCK=UNAVAILABLE`. Organizer has a database writer flock,
completion orchestration has a separate global operation lock, and Stage12
has its own singleton runner lock. None is a shared per-title lock held by
these producers and the web deletion route. Double activity checks close the
writer-preflight interval but leave a TOCTOU window after the second check and
before the first exact unlink. Therefore `CANARY_READY=NO`; do not enable the
gate or select/delete a canary until this cross-worker race is closed or a
separately verifiable operational exclusion is approved.

Offline target-activity, writer, prepare/validate, commit/partial-recovery,
Library API/UI, File Management navigation, subtitle status and Discovery
smokes passed. Python compile, `git diff --check`, and full local Docker build
passed. Production deploy = NO; production gate remains false/effectively
disabled; production DB/NAS/provenance/Jellyfin mutations = 0, subtitle
generation/Hermes/VM122 = 0, actual delete = 0. Next: resolve the shared
per-title exclusion/race, then repeat F2D final preflight before any canary.

## Stage13-F2I unexpected media retry forensic — INCOMPLETE / CANARY BLOCKED, 2026-09-29

Source/runtime identity was checked read-only: checkout and remote branch are
both `807d400999febdb8e13a5d70a624f75477785d16`; production web image remains
`sha256:bac75af6716cd7a0e33aa671b90f9386926d8dc93f64dba201caa6494283e404`.
The web app is running with delete gate false. The completion timer remains
enabled but inactive; its last trigger was 2026-09-29 12:31:56 KST and its
one-shot service exited successfully at 12:31:57 KST. No timer/service action
was performed during this forensic.

The bounded incident journal reports completion `total=0`, `eligible=0`,
`applied=0`, media reconciliation `0`, and one retry attempted, zero completed,
one failed. The exact media state row is `media_job_id=174261`,
`dvd_id=MFCS-085`, status `FAILED`, `attempt_count=17161`, updated at
`2026-09-29T03:31:57Z`. The stored error was examined without printing its
contents; it did not match the pinned runtime's known safe error literals, so
the safe classification remains `UNCLASSIFIED_ERROR` and
`FAILURE_STAGE=FAILURE_STAGE_UNKNOWN`.

The current exact Discovery holding is holding 165, `MFCS-085`,
`MFCS/MFCS-085/MFCS-085.mp4`, present=1, discovered by `completion-stage9`,
size 1,467,881,427 bytes and mtime_ns 1788865655288182673. A bounded direct
listing of only that canonical title directory found the regular media file
and `MFCS-085.ko.srt`; the media size/mtime matches the holding. No current
NFO/poster sidecar or `.teddy-stage9-meta-*.partial` entry was found. This is
current-state evidence only, without an incident-time baseline; therefore
`NAS_METADATA_SIDE_EFFECT=UNKNOWN`.

Jellyfin was queried GET-only. One current item matches the exact canonical
media path. This does not establish whether this invocation sent its notify
POST, so `JELLYFIN_SIDE_EFFECT=UNKNOWN`.

Pinned F2F source audit: `run_retryable_media_jobs()` marks each selected job
RUNNING/increments attempts, invokes its processor, then records FAILED on an
exception. The completion runner calls this retry path after the separately
locked completion `process_one()` loop. The retry path does not acquire the
shared title lock; neither `run_media_pipeline()` nor its NAS metadata publish
and Jellyfin notify stages are within that per-title lock. Thus
`MEDIA_RETRY_TITLE_LOCK=NO`. FAILED rows remain retryable and the runner has no
per-job retry ceiling/backoff, so resuming the timer risks repeatedly running
this same row. `COMPLETION_TIMER_SAFE_TO_RESUME=NO`.

The separate `teddy-discovery-jav-reconcile-apply.service` is an inactive,
manual one-shot with no apply timer attached (the scheduled reconcile unit is
report-only). Its pinned launcher currently targets the old mutable
`/opt/missav-dlp-web/stage9-runtime`; apply performs a bounded remote library
reconciliation and can update Discovery holdings under the global
`teddy-discovery-jav-library-operation.lock`. It has no per-title lock. The
delete path does not take that global lock, so it is not mutual exclusion with
delete. Freeze manual apply around any future delete canary until an explicit
exclusion contract is implemented:
`RECONCILE_APPLY_LOCK_VERDICT=NEEDS_SEPARATE_OPERATIONAL_FREEZE`.

No retry, repair, reconcile apply, prepare/validate/commit/resume, NAS action,
Discovery write, provenance write, Jellyfin write/refresh, subtitle work,
Hermes/VM122 call, or delete occurred in this checkpoint. Current completion
timer is still inactive. `CANARY_READY=NO`; blockers are missing shared title
exclusion on media retries, unknown incident side-effect stage, unbounded
retry behavior, and the manual reconcile-apply exclusion gap. Next: implement
and offline-test a retry-specific title-lock boundary with bounded retry
semantics, then define the reconcile-apply/delete exclusion and repeat a
read-only production preflight. Do not resume the completion timer meanwhile.

## Stage13-F2J media retry exclusion and bounded policy — PASS, source/fixture only, 2026-09-29

F2I incident evidence remains unchanged: media job 174261 / `MFCS-085` is
FAILED at 17,161 attempts; its exact failure stage and incident-time NAS
metadata/Jellyfin effects remain UNKNOWN. No production retry or repair was
performed.

`teddy_discovery_media_jobs.py` now uses the existing
`teddy_title_exclusion.try_acquire_title_lock()` with
`TEDDY_TITLE_LOCK_DIR`. The retry acquires the title lock before conditional
RUNNING transition and retains it through processor completion and durable
COMPLETED/FAILED update. This covers NAS metadata publication and Jellyfin
notification in the existing media pipeline. BUSY returns
`HELD_TITLE_BUSY`; missing/invalid/unavailable lock infrastructure returns
`TITLE_LOCK_UNAVAILABLE`. Either outcome leaves the media row and attempt
count unchanged and never calls the processor.

Retry policy uses existing `status`, `attempt_count`, and `updated_at`
columns; no schema migration was added. Defaults are max attempts 5, FAILED
backoff 3,600 seconds, and RUNNING stale threshold 7,200 seconds. PENDING is
immediately eligible below the attempt cap. FAILED is eligible only after the
backoff; RUNNING is eligible only after the stale threshold; malformed or
timezone-naive required timestamps are held. COMPLETED is never retried and
at/above-cap jobs are EXHAUSTED. Thus the known 17,161-attempt fixture maps to
EXHAUSTED / not automatically eligible. There is no production manual retry
override in this change.

After acquiring the title lock, the runner starts the existing short media
writer transaction, rereads the row and re-evaluates eligibility, then uses a
conditional UPDATE on job ID, DVD-ID, expected status, attempt count, and
updated_at. A changed/deleted row is held as `HELD_CONFLICT`; processor is not
called. Lock order is title lock then media writer lock; no path was found
that holds the media writer lock while acquiring a title lock. The media
pipeline stage order itself is unchanged.

Fixture coverage passed for retry eligibility/backoff/stale/exhaustion,
malformed timestamps, title-lock BUSY/unavailable, lock held through
processing/final state, exception release, distinct-title progress, and
candidate row status/attempt/timestamp/removal races. Existing title-lock
process tests confirmed same-title BUSY, different-title parallelism and
process-exit release. Existing delete commit fixture confirmed a same-title
holder produces `delete_target_busy` before NAS mutation.

The broad `teddy-discovery-jav-reconcile-apply.service` remains unchanged.
It is a manual one-shot using the global operation lock, which delete does
not share. Therefore `CANARY_RECONCILE_APPLY_FREEZE_REQUIRED=YES`: during a
future actual delete canary, verify the apply service inactive, verify no
related process is running, and prohibit the supported apply launcher until
the destructive window ends. The exact production freeze procedure still
requires a read-only deployment/preflight checkpoint.

Offline media jobs/pipeline/publish, completion runner/media/orchestrator,
organizer, title exclusion, Stage12 batch/bulk/rollout/retry, F1 delete commit,
activity guard, Discovery writer, E1 prepare/validate, Library API/UI,
File Management navigation, subtitle status, Discovery, Python compilation,
`git diff --check`, and full Docker image build passed. The initial system
Python attempts for Flask-dependent smokes were rerun successfully in the
built Docker runtime; Stage12 retry smoke passed in its required
`/opt/stage11-stt-venv` interpreter.

Production deploy = NO. Completion timer remains inactive/enabled and was not
started; delete feature gate remains false. Production media/Discovery/
provenance DB writes, NAS writes/deletes, Jellyfin notify/refresh, organizer
publish, Stage12 processing, Hermes/VM122 calls, and actual delete = 0.
`MEDIA_RETRY_TITLE_LOCK=YES`, `MEDIA_RETRY_BOUNDED=YES`,
`MFCS085_AUTOMATIC_RETRY_ELIGIBLE=NO`,
`CANARY_RECONCILE_APPLY_FREEZE_REQUIRED=YES`, and
`COMPLETION_TIMER_SAFE_TO_RESUME=NO` because this change is not deployed.
Next: deploy the new pinned completion runtime, then read-only inspect eligible,
exhausted and backoff-held counts while leaving the timer stopped; repeat
canary safety preflight. No canary title is approved by this result.

## Stage13-F2K bounded media runtime rollout and read-only canary preflight — PASS / CANARY_READY=YES, 2026-09-29

The exact source commit `705bf9e700156d88523babfad15861a5faee9ff2` is
installed at immutable, root-owned mode-0555 release
`/opt/missav-dlp-web/stage9-runtime/releases/705bf9e700156d88523babfad15861a5faee9ff2/`.
It contains the 24 project-local Python modules in the prior completion runtime
closure, not a repository copy. Every installed module was SHA-256 compared
against `git show 705bf9e...:<path>`; all matched. The release marker identifies
the exact commit. The required media jobs, title exclusion, completion runner,
and completion orchestrator blobs matched. Offline imports and media jobs,
completion runner, and process-level title-lock smoke ran with the new release
and `/usr/bin/python3`; all passed.

The old completion wrapper was preserved byte-for-byte at
`/usr/local/sbin/teddy-completion-stage9-runner.backup-26c8657d4bd5c5b767f2f8eb474a80ff9121a150`.
The wrapper was atomically switched to the new release without executing it.
It sets `TEDDY_TITLE_LOCK_DIR=/opt/missav-dlp-web/title-locks`, sets
`PYTHONPATH` only to the new release, and retains the existing runner arguments.
`bash -n` passed. The systemd completion service defaults to root:root
(uid/gid 0:0), `/usr/bin/python3`, and imports from the exact 705 release.
The source tree `/opt/missav-pwa-subtitle-stage11` is not the runtime import
path; no old release path is added to `PYTHONPATH`.

Production media state was opened with SQLite `mode=ro` and
`PRAGMA query_only=ON`; no initializer or runner was called. Across the 20
PENDING/FAILED/RUNNING rows, the new pure policy classifies ELIGIBLE=19,
HELD_BACKOFF=0, HELD_FRESH_RUNNING=0, HELD_INVALID_TIMESTAMP=0,
HELD_INVALID_STATE=0, EXHAUSTED=1. Overall media statuses are COMPLETED=34,
PENDING=19, FAILED=1, RUNNING=0. The exact `MFCS-085` row remains job 174261,
FAILED, attempt_count=17161, and classifies EXHAUSTED. Source/fixture semantics
skip EXHAUSTED rows before lock acquisition, conditional RUNNING update, or
processor call. `MFCS085_AUTOMATIC_RETRY_ELIGIBLE=NO`.

Runtime title-lock verification used the pinned release Python on host and the
running web container at `/run/teddy-title-locks`. The host path is
`/opt/missav-dlp-web/title-locks`; the bind mount is the same host-backed
RW directory. For `ADN-785`, web-held → pinned-host attempt returned BUSY and
pinned-host-held → web attempt returned BUSY. After release both sides
acquired successfully. While the host held `ADN-785`, the web acquired
`MFCS-085`, confirming per-title concurrency. Host and container observed the
same regular lock-file device/inode (1796:548311), mode 0600. The shared root
is mode 0750 root:root. These are connectivity probes only, not a canary-title
selection.

Static audit confirms retry policy eligibility is evaluated before lock
acquisition; title lock is acquired before conditional RUNNING transition;
processor and final durable state update remain inside the title-lock scope.
The processor calls the unchanged media pipeline, whose metadata publish and
Jellyfin notify stages therefore remain locked. The title lock is outer to the
media-state writer transaction; no media writer-lock-held path was found that
then acquires a title lock. Organizer/completion still acquires title lock
before the global operation lock. `MEDIA_RETRY_LOCK_ORDER=PASS`.
The web container still has `TEDDY_TITLE_LOCK_DIR=/run/teddy-title-locks`,
`TEDDY_LIBRARY_DELETE_ENABLED=false`, Discovery DB mounted read-only, and
writer health READY. The existing delete commit/resume path uses the same
per-title primitive; no delete endpoint was called.

The completion timer is enabled but inactive; completion service is inactive.
No start/restart, service run, timer restoration, or daemon reload occurred.
`COMPLETION_TIMER_POLICY_READY=YES`; `COMPLETION_TIMER_RESUMED=NO`.
The separate `teddy-discovery-jav-reconcile-apply.service` is inactive and is
a manual one-shot with no apply timer. Its current wrapper/runtime target is
the old `/opt/missav-dlp-web/stage9-runtime` tree; its reconciliation source
uses the global operation lock
`/run/lock/teddy-discovery-jav-library-operation.lock`. The scheduled
`teddy-discovery-jav-reconcile.timer` points to report-only service, not apply.
Using the exact new runtime `operation_lock()` primitive in separate processes,
a short lock-only probe returned ACQUIRED for the holder, BUSY for a second
process while held, and ACQUIRED after release. No reconcile service ran.
Therefore `CANARY_RECONCILE_FREEZE_READY=YES`.

Frozen actual-canary operational procedure: (1) confirm completion timer
inactive; (2) confirm reconcile-apply service inactive and no related process;
(3) hold the global operation lock with a no-I/O freeze holder; (4) verify the
holder; (5) run target-specific activity and title-lock preflight; (6) keep the
freeze holder through the delete/reconciliation window; (7) confirm Discovery
and Jellyfin reconciliation, gate false, then release the holder; (8) decide
timer resumption separately. The lock holder performs no DB/NAS/Jellyfin I/O
and is short-lived in this checkpoint. This canary-only freeze does not change
normal global serialization.

Current read-only activity snapshot: organizer active=0; Stage12
RUNNING/GENERATED=0; heartbeat is present but stale (`COMPLETE`, no current
DVD-ID). No Stage12 systemd/cron automatic launcher was found. Current present
JAV holdings=184, unique DVD-ID=184, duplicates=0, canonical/parse mismatches=0.
No active conflicting job was observed. Eligible pending media jobs remain
stopped with the completion timer.

The F2I incident remains historically unresolved: its failure stage,
NAS metadata side effect, and Jellyfin side effect are still UNKNOWN, not
silently cleared. Per the F2K decision rule, that historical uncertainty does
not itself block a different future canary now that the failed row is
EXHAUSTED and bounded runtime/lock/freeze controls are verified.

`CANARY_READY=YES`. The deployed web app image remains
`sha256:bac75af6716cd7a0e33aa671b90f9386926d8dc93f64dba201caa6494283e404`;
delete feature gate=false. Production mutation was limited to the immutable
completion runtime install, wrapper backup/atomic switch, and lock-only
probes. Media/Discovery/provenance DB writes, NAS metadata/delete, organizer
publish, Jellyfin notify/refresh, Stage12 work, delete commit/resume/reconcile,
Hermes/VM122 calls, and actual permanent delete = 0. Next: stop code changes
and ask Teddy to select one intended canary title. Require separate final
irreversible confirmation immediately before any actual delete; do not enable
the gate before that approval.

## Stage13-F2L — VEMA-246 read-only target preflight

Teddy selected `VEMA-246` as a canary candidate. This selection is not
authorization to permanently delete it. This checkpoint performed no prepare
or validate HTTP request because no safe authenticated browser session was
available for reuse (`AUTHENTICATED_PREPARE=NOT_REPLAYED`). No token was issued.

Git preflight was clean at source HEAD
`c06f83ab2af2fa9495663fc9f4e93bbb8cce2ca1`, branch
`teddy-subtitle-stage11`, equal to the exact remote branch head. Production web
was running the F2F image
`sha256:bac75af6716cd7a0e33aa671b90f9386926d8dc93f64dba201caa6494283e404`
with restart count 0. `TEDDY_LIBRARY_DELETE_ENABLED=false`, title-lock config
was `/run/teddy-title-locks`, and the Discovery writer health operation
returned READY. Completion runtime marker remained
`705bf9e700156d88523babfad15861a5faee9ff2`; completion timer and service and
the reconcile-apply service were inactive. The reconcile-apply path remains a
manual one-shot with no automatic apply timer; F2K's short global-lock
contention evidence keeps `CANARY_RECONCILE_FREEZE_READY=YES`.

The Discovery DB was opened `mode=ro` with `PRAGMA query_only=ON`. Exactly one
present JAV holding matched: holding_id=20, DVD-ID `VEMA-246`,
`VEMA/VEMA-246/VEMA-246.mp4`, `MATCHED`, size 2,844,299,563 bytes,
mtime_ns=1788054184863651608, discovered_by `library-inventory`. The deployed
canonical mapping agreed on family `VEMA`, directory `VEMA/VEMA-246`, media
filename `VEMA-246.mp4`, and extension `.mp4`.

The exact title directory was inspected over the hardened NAS SSH transport
using lstat on root/family/title and direct entries only. All four entries
were regular files; there were no symlinks, nested directories, special files,
unsafe names, or path normalization/containment failures. Canonical manifest
identity SHA-256 (metadata identity, not content hash) was
`121aefa01eb2d6cd9ae6b99695892cf4652aa4b33d50e65a4c3208b6ef3c8677`, with
4 files totaling 2,844,317,586 bytes. The canonical media size and mtime_ns
matched the holding. Filenames: `VEMA-246.ko.srt` (KO subtitle),
`VEMA-246.mp4` (video), `movie.nfo`, and `poster.webp`; no JA/EN subtitle was
present. Subtitle file contents were not read or output. No absolute NAS path
was included in the manifest report.

Target state was read by exact DVD-ID. The latest organizer job (job_id=56)
was `COMPLETED`; the Stage12 rollout row was `PUBLISHED`, which is terminal
under the current status contract (active states are RUNNING/GENERATED). The
heartbeat was stale `COMPLETE` with no current DVD-ID. No media job row
existed, so `TARGET_MEDIA_JOB=NONE`. The production activity guard returned
IDLE. `TARGET_MEDIA_READY=YES`.

The production Jellyfin reconciler's bounded read-only GET path returned
exactly one item matching `/media/adult/VEMA/VEMA-246/VEMA-246.mp4`.
No Jellyfin mutation was called. The host writer's `preflight_holding`
returned READY; this is the writer's BEGIN IMMEDIATE / exact validation /
ROLLBACK preflight. The target title lock returned ACQUIRED on both host and
web container and was immediately released. Host and container observed the
same lock-file device/inode (1796:548375); the file was regular, mode 0600.

Before/after read-only snapshots were unchanged: VEMA-246 remained present=1
with the same holding identity; current present JAV holdings remained 184,
unique DVD-ID count 184, duplicate count 0, and canonical/parse mismatch count
0. No conflicting completion/reconcile/Stage12/subtitle process was observed.
Completion timer remained inactive (enabled, not started); reconcile-apply
remained inactive; delete gate remained false. The production web app received
no prepare, validate, commit, resume, or reconcile request. Discovery content,
media state, durable provenance, NAS, and Jellyfin were not mutated; actual
delete=0.

`TARGET_CANARY_READY=YES`, subject to a separate final irreversible approval.
This means only that the read-only preflight passed. It does not authorize
enabling the feature gate, performing a fresh prepare/validate, or deleting
VEMA-246. Next: present this evidence to Teddy and obtain explicit final
confirmation for VEMA-246 immediately before a separate actual-delete
checkpoint. Until then, keep the gate false and do not prepare, validate, or
commit.

## Stage13-F2M-A / F2M-A2 — ARM withdrawn after UI prepare failure

F2M-A received Teddy's explicit final confirmation for VEMA-246, with actual
commit reserved for the authenticated user UI. Fresh holding/manifest/activity/
writer/title-lock checks matched F2L. A transient Compose override enabled the
gate on the unchanged F2F image; a supervised global operation lock holder and
10-minute watchdog were started. The completion timer was disabled without
starting it. Web restart policy was temporarily `no`; base Compose/env stayed
gate=false. No authenticated request or actual deletion was performed by Codex.

Teddy's UI prepare then failed. F2M-A2 immediately stopped the watchdog timer
and executed its disarm procedure, before its planned 14:51:08 KST expiry.
DISARM returned PASS. The override was removed and only web was recreated from
base production Compose. Gate=false, expected image
`sha256:bac75af6716cd7a0e33aa671b90f9386926d8dc93f64dba201caa6494283e404`,
running, restart policy `unless-stopped`, login HTTP 200, writer READY, and
Discovery mount RO were verified. Freeze-holder/watchdog are inactive; the
global lock has zero holders and all three ARM temporary files are gone.
Completion timer remains inactive/disabled; completion service and
reconcile-apply remain inactive. No re-ARM or timer resumption occurred.

The bounded ARM-container access log showed VEMA-246 prepare POST HTTP 503 at
2026-09-29 14:46:25 and 14:46:42 KST. No guard-rejection line was found in the
captured window. The response body was not retained, so a wire-observed JSON
error code or logged exception cannot be claimed. Deployed source and runtime
configuration establish the precise failure branch: all four `TEDDY_NAS_*`
variables are absent, `_nas_client_from_env()` returns None, and the production
blueprint receives no injected NAS reader. Thus `delete_manifest_reader` is
None and `current_delete_snapshot()` raises
`DeleteDryRunError("NAS_INSPECTION_UNAVAILABLE", 503)` before holding inventory
or token issuance. Its caught response code is `nas_inspection_unavailable`;
this caught branch does not log an exception. This code is source/config-derived
evidence, not a captured response body. No prepare/validate/commit was replayed.

Canonical Compose and both ARM/gate-off runtime lack `TEDDY_NAS_HOST`,
`TEDDY_NAS_USER`, `TEDDY_NAS_KEY`, `TEDDY_NAS_KNOWN_HOSTS`,
`TEDDY_JELLYFIN_URL`, and `TEDDY_JELLYFIN_KEY`. NAS key/known_hosts files exist
and are readable by web uid/gid 0:0 at `/run/secrets/teddy-nas-transfer/`;
the suggested `/run/secrets/teddy-nas/` paths do not exist. The missing NAS env
prevents use of the existing readable key mount. The Jellyfin key mount at
`/run/secrets/teddy-jellyfin/api_key` is absent. No secret contents were printed.

Normalized mount source/target/mode/type sets, env-name sets, image, network
mode/attachments and supplementary groups match between ARM and gate-off.
Only the intended gate value and temporary restart policy differ.
`ARM_CONTAINER_CONFIG_MATCH=YES` for the canonical deployment configuration;
that configuration itself is incomplete for Library NAS/Jellyfin dependencies.
There is no evidence that the ARM override removed those dependencies, or that
they existed in the pre-ARM web container. F2L's successful NAS/Jellyfin checks
used explicitly configured host helpers, so they did not prove web runtime
dependency wiring. The earlier readiness claim was too broad.

`ROOT_CAUSE=CANONICAL_WEB_NAS_JELLYFIN_CONFIG_MISSING`.
Gate-off configured container probes remain unavailable (NAS client None,
Jellyfin LibraryError before HTTP). Its actual read model still returns 184
titles, known bytes=0, size-unknown=184, KO-valid=0; VEMA-246 managed size is
unknown, KO UNRESOLVED, Jellyfin UNKNOWN. Configuration was intentionally not
repaired in this forensic checkpoint. `UI_SAFE_CODE_MISMATCH=YES`: frontend
allows `nas_inventory_unavailable` but omits `nas_inspection_unavailable`,
explaining the generic UI message independently of the missing configuration.

Independent exact-target read-only safety evidence: holding 20 remains
present=1/MATCHED at `VEMA/VEMA-246/VEMA-246.mp4`, size=2844299563,
mtime_ns=1788054184863651608; present JAV count remains 184. Dedicated host
NAS SSH lstat confirms all four original regular files (`VEMA-246.mp4`,
`VEMA-246.ko.srt`, `movie.nfo`, `poster.webp`), total 2844317586 bytes, and
unchanged manifest SHA
`121aefa01eb2d6cd9ae6b99695892cf4652aa4b33d50e65a4c3208b6ef3c8677`.
Host GET-only Jellyfin lookup still finds one exact canonical item. No
provenance-path override is configured and the default persistent provenance
DB does not exist, so no target operation record was created. `ACTUAL_DELETE=0`.

F2M-A2 verdict: INCOMPLETE; safely disarmed, root cause established, Library
runtime regression persists pending an authorized config/source fix. No NAS,
Discovery/media DB, provenance, Jellyfin, completion, Stage12, or delete
mutation was performed. Only fail-safe web recreation, transient cleanup, and
this handoff update occurred. Next checkpoint should repair canonical NAS/
Jellyfin env and mounts and the UI safe-code allowlist, verify from the actual
gate-off web container, and keep the gate false until a separately requested
ARM. Do not resume the completion timer automatically.

## Stage13-F2M-A3 — repair production NAS/Jellyfin wiring drift

The repository's canonical `docker-compose.gluetun.yml` already defined all
six `TEDDY_NAS_*`/`TEDDY_JELLYFIN_*` variables and the dedicated read-only NAS
key, known_hosts, and Jellyfin key mounts. Production
`/opt/missav-dlp-web/compose.yaml` had omitted those runtime variables and file
mounts; it also retained the old Stage12 rollout DB container target. Therefore
`PRODUCTION_COMPOSE_DRIFT=YES`. The production web service stanza was minimally
repaired to match the canonical NAS/Jellyfin values and mounts and to use the
canonical `/discovery/stage12-rollout-state.sqlite3` target. The previous
production Compose file is retained at
`/opt/missav-dlp-web/compose.yaml.pre-f2ma3-20260929-1453`. No other service
was recreated.

The web-only image was built from source commit
`3dc801a9b9c9f6be9210fbb2b15045cc12ee4fa3`, image ID
`sha256:e90c320f44b9b3249093f989979805d5ec9861663bb03af35f91b7a6a5920807`,
and deployed with the gate false. In-container checks confirmed the six
variables are present; all three secret files are regular/readable and mounted
read-only. Discovery remains `:ro`, writer socket `:ro`, title-lock directory
`:rw`, and Stage12 DB `:ro`. Writer health is READY, login is HTTP 200,
unauthenticated `/api/library` is HTTP 401, and Library JS is HTTP 200.

Using the production container's configured NAS code for the exact target,
VEMA-246 still has four direct files (`VEMA-246.ko.srt`, `VEMA-246.mp4`,
`movie.nfo`, `poster.webp`), total 2,844,317,586 bytes, and manifest SHA
`121aefa01eb2d6cd9ae6b99695892cf4652aa4b33d50e65a4c3208b6ef3c8677`.
The exact Jellyfin GET lookup finds one item. Production blueprint construction
has both `delete_manifest_reader` and `delete_mutator` configured; no prepare
route was called and no token was issued.

The production Library read model now reports 184/184 known sizes, 0 unknown,
163 valid KO subtitles, 10 unresolved, 11 absent, 0 mismatch, and 545,315,128,474
known bytes. VEMA-246 reports size 2,844,317,586, KO `VALID`, Jellyfin
`RECOGNIZED`, and mismatch false. The UI safe-code allowlist now includes
`nas_inspection_unavailable` while retaining `nas_inventory_unavailable`;
the UI smoke fixture and full Docker build passed.

Final state: `TEDDY_LIBRARY_DELETE_ENABLED=false`; completion timer/service and
reconcile-apply remain inactive; no freeze-holder or watchdog remains. The
provenance DB/operation record is absent, holding 20 remains present=1, and
the four NAS manifest entries remain present. No prepare/validate/commit,
Discovery/media/provenance write, NAS mutation, Jellyfin mutation, completion,
Stage12, or reconcile apply occurred. `ACTUAL_DELETE=0`.

F2M-A3 verdict: PASS for the configuration repair and gate-off runtime
regression. Next, Teddy should verify the restored Library screen and, with
the gate still false, click `영구 삭제 준비` once to confirm the manifest is
shown. Do not re-arm until that gate-off prepare display is confirmed.

## Stage13-F2M-A5 / A6 — watchdog hardening and gate-false rehearsal

F2M-A5 verified the 10-minute watchdog triggered at 2026-09-29 15:33:51 KST
and exited 1 at 15:34:12 KST. Its base Compose gate-off recreation completed,
but it treated container state `running` as sufficient to issue only one
immediate `/login` request. That request got connection-reset while Flask was
still starting. The fail-safe branch then stopped web and retained the global
freeze. Gate-off configuration had been applied; the failed readiness check,
not a delete path, caused the watchdog failure. Web was subsequently started
from the base gate-false Compose, `/login` returned 200, and only then was the
freeze released. Gate was never re-armed and no delete request was sent.

Added reusable deployment helper
`deploy/stage13-f2m/canary_disarm.py` and deterministic fixtures in
`deploy/stage13-f2m/canary_disarm_smoke.py`. It verifies canonical Compose
gate=false/image/restart policy, recreates only `missav-dlp-web`, and polls
container-running plus local `/login` HTTP 200 every 2 seconds for at most 120
seconds. It then checks writer READY, required read/write mount modes, runtime
gate=false, and restart policy `unless-stopped`. Only after all checks does it
release an active freeze-holder and stop the transient watchdog timer. When
freeze is absent it remains idempotent for watchdog recovery; a rehearsal may
explicitly require a holder. Any pre-release failure stops web, sets restart
policy `no`, returns nonzero with a bounded safe reason, and never releases an
active freeze. It does not inspect or print secret values and issues no delete
API request.

Offline fixtures passed for immediate readiness, 24-second delayed readiness,
transient connection/HTTP errors followed by 200, timeout fail-safe, writer
failure, gate mismatch, restart-policy mismatch, exception ordering, all
idempotent gate/web/freeze states, and safe error output. Python compile,
`git diff --check`, Compose render, Library UI smoke, Library API fixture smoke,
and Discovery writer fixture smoke passed. The API/writer fixture smokes were
run inside the production image because host Python has no Flask dependency.

Gate-false production rehearsal used a supervised holder with the pinned
completion `operation_lock()` primitive. An independent contender observed
BUSY. A 30-second transient systemd timer invoked the new helper while gate
remained false. The helper recreated only the web app, observed local
readiness after 15.767 seconds, verified writer/mount/gate/restart policy, and
then released the freeze. Its systemd service completed successfully; the
timer and service are now inactive/collected. No completion/reconcile service
was run.

Post-rehearsal: gate=false, web running on image
`sha256:e90c320f44b9b3249093f989979805d5ec9861663bb03af35f91b7a6a5920807`,
restart count 0, policy `unless-stopped`, login 200, writer READY, Discovery
and writer mounts RO, title-lock RW. Freeze-holder is inactive and the global
operation lock probe acquired/released. Completion timer remains inactive and
disabled; completion service and reconcile-apply are inactive. VEMA-246
holding 20 remains present=1; four files, 2,844,317,586 bytes, manifest SHA
`121aefa01eb2d6cd9ae6b99695892cf4652aa4b33d50e65a4c3208b6ef3c8677`, Jellyfin
exact count 1, and Library size/KO/Jellyfin state remain unchanged. Provenance
DB/operation is absent. `ACTUAL_DELETE=0`.

`DISARM_WATCHDOG_HARDENED=YES`, `GATE_FALSE_REHEARSAL=PASS`,
`POST_REHEARSAL_SAFE=YES`. Gate remained false throughout. Next action is a
separately requested short ARM only after this evidence is reviewed; do not
prepare, validate, commit, or delete as part of this rehearsal.

## Stage13-F2M-B — VEMA-246 actual-delete forensic

Teddy executed the previously approved VEMA-246 permanent delete through the
authenticated Downloader UI. This checkpoint performed read-only forensic
inspection only; it did not call commit/reconcile/resume or any writer mutation.

The single provenance operation is
`e8b5ba23-cb6d-4e5e-81f6-c1e5fdb79873`, bound to DVD-ID VEMA-246 and holding 20.
Its manifest SHA is
`121aefa01eb2d6cd9ae6b99695892cf4652aa4b33d50e65a4c3208b6ef3c8677`, with four
files and 2,844,317,586 bytes. The removed set is exactly
`VEMA-246.ko.srt`, `VEMA-246.mp4`, `movie.nfo`, and `poster.webp`; removed count
and bytes match, remaining entries are empty, and `nas_delete_complete=1`.
The exact NAS title directory `/volume1/video/video2/JAV/VEMA/VEMA-246` is
absent, and direct exact-path checks found all four files absent:
`NAS_DELETE_COMPLETE=YES`, `ACTUAL_FILE_DELETE=YES`.

Discovery row 20 remains canonical (`storage_root=jav`, `parse_status=MATCHED`)
and `present=1`. The provenance row has `discovery_reconciled=0`,
`jellyfin_reconciled=NULL`, and `result_state=RECONCILE_PENDING`.
The exact Jellyfin GET lookup still finds one item at the old media path. The
web warning at 17:05:50 KST records `Library delete Discovery reconcile pending
(WriterError)`. This establishes that the writer call failed, but the log only
records the exception type, not its safe writer error code. No commit access
log line was retained; the UI reported `RECONCILE_PENDING`, which the source
returns as HTTP 202 for a pending commit result. The source stops before
Jellyfin reconciliation when Discovery writer reconciliation fails, so the
Jellyfin step was not reached and the provenance flag remains NULL.

Classification: `PENDING_STAGE=DISCOVERY`,
`DISCOVERY_PROVENANCE_CRASH_WINDOW=NO` (the holding is still present, so this
is not the present=0/provenance=0 crash window),
`DISCOVERY_RECONCILED=NO`, `JELLYFIN_RECONCILED=NO`, and
`DELETE_OPERATION_FINAL=NO`. The Library read model correspondingly shows the
VEMA-246 row with unknown managed size and unresolved KO state while its stale
Jellyfin item remains recognized. Do not mark the holding absent or alter
provenance manually; the next recovery checkpoint should address only the
Discovery reconciliation for this exact operation, then re-read state before
any Jellyfin action.

The F2M-A7 watchdog ran at 17:08:21 KST and completed at 17:08:37 KST with
`DISARMED` and readiness time 15.501 seconds. Current safe state: delete gate
false, web running on `sha256:e90c320f44b9b3249093f989979805d5ec9861663bb03af35f91b7a6a5920807`,
restart policy `unless-stopped`, `/login` 200, writer READY, operation lock
free, freeze-holder/watchdog inactive, completion timer/service inactive, and
reconcile-apply inactive. No re-arm occurred. The reconcile operation remains
pending and must not be retried until its failure is addressed in the next
explicit checkpoint.

## Stage13-F2M-C — exact Discovery recovery preflight (INCOMPLETE)

Read-only investigation confirmed the writer service runs as `root` in group
`teddy-library-discovery-writer`, from the immutable F2B release
`09a3a89bac6af910ca3543f8c076bb0f54e2cb41`. Its configured Discovery and
provenance paths are the canonical host files. Device/inode checks matched
web `/discovery/teddy-discovery.sqlite3` to the host Discovery DB and web
`/downloads/teddy-library-delete-provenance.sqlite3` to the host provenance
DB. Both databases report WAL mode. The service is active; web gate is false
and writer health is READY.

For operation `e8b5ba23-cb6d-4e5e-81f6-c1e5fdb79873`, the writer's current
read-only `_provenance()` validation passes against the durable operation,
and its read-only `_row()` identity check passes for holding 20 / VEMA-246
with `present=1`. A current `preflight_holding` returns READY. The retained
17:05:50 KST web log records only `WriterError` for Discovery reconciliation;
it does not record `WriterError.code`, and the commit access-log line is not
retained. Therefore `WRITER_ERROR_CODE=UNKNOWN_NOT_RETAINED` and the original
failure cannot be assigned an exact root cause from available evidence.
Possible transient transport/database causes are not asserted as fact.

Per the fail-closed requirement, no writer `mark_absent`, recovery helper,
HTTP reconciliation endpoint, or production database mutation was run. The
crash-window journal hardening was not deployed, and the exact operation is
still pending: holding 20 `present=1`, provenance `discovery_reconciled=0`,
NAS deletion complete, Jellyfin flag NULL and exact GET item count 1.
`WRITER_ROOT_CAUSE_RESOLVED=NO`,
`DISCOVERY_CRASH_RECOVERY_HARDENED=NO`, `DISCOVERY_RECONCILED=NO`.

Production remains safe: gate false, web healthy on the repaired image, writer
READY, completion timer/service and reconcile-apply inactive, no title/global
lock held, NAS title directory absent. The next checkpoint must not claim the
original error code without evidence. It should preserve the original
operation, add the requested atomic Discovery journal recovery and safe writer
error-code observability, validate fixtures, then use only that exact
operation if the recovery preconditions pass. Jellyfin remains a separate
later action.

## Stage13-F2M-C2 — crash-safe writer hardening and exact check-only

`HISTORICAL_WRITER_ERROR_CODE=UNKNOWN` remains unchanged. The earlier log
recorded only the `WriterError` class; current successful validation does not
identify the historical failure, and no cause is inferred.

The exact operation remains
`e8b5ba23-cb6d-4e5e-81f6-c1e5fdb79873` for VEMA-246 / holding 20. Source commit
`3daac14029ad049416373fa2c452a47a64c9b732` adds the narrow
`library_delete_reconcile_journal` contract. Its table is created only inside
`mark_absent`'s `BEGIN IMMEDIATE` transaction. Journal insertion and the exact
conditional `present=1 -> 0` update commit atomically. A repeated exact
operation with `present=0` and a matching journal returns
`ALREADY_RECONCILED`; absent rows without a matching journal, foreign
operations, or identity drift fail with `OPERATION_MISMATCH`. Health and
preflight do not create the table. Fixture coverage includes crash-after-writer
commit recovery, mismatched/no journal, provenance flag still zero, rollback
on journal/holding failure, and repeat after provenance is marked.

Writer/client error logging now preserves only bounded safe fields: operation,
DVD-ID, holding ID, and allowlisted `WriterError.code`. It omits fingerprints,
tokens, raw request JSON, and sensitive paths. Fixtures cover provenance,
identity, busy, unavailable, and protocol codes and verify sensitive values do
not appear in logs.

The immutable production writer release is
`/opt/missav-dlp-web/teddy-library-discovery-writer/releases/3daac14029ad049416373fa2c452a47a64c9b732/`,
verified against source commit `3daac14029ad049416373fa2c452a47a64c9b732`.
The writer service alone was updated and restarted; it is active/enabled and
uses the canonical Discovery/provenance files. Health and exact holding
preflight return READY. After restart and health/preflight, the journal table
was still absent, confirming startup/readiness caused no Discovery schema
write.

The strict read-only helper
`deploy/stage13-f2m/reconcile_discovery_pending.py --check-only` returned
`RECOVERY_ELIGIBLE=YES` for the exact operation, VEMA-246, holding 20, four
removed files, and 2,844,317,586 bytes. It confirmed exact durable provenance,
current holding identity and `present=1`, no duplicate present holding, target
activity IDLE, and absent exact NAS title directory. It has no apply mode and
does not call the writer. The historical exact manifest SHA remains
`121aefa01eb2d6cd9ae6b99695892cf4652aa4b33d50e65a4c3208b6ef3c8677`.

At checkpoint end, production mutation counts for Discovery content/schema,
journal, provenance, NAS, and Jellyfin were all zero. Holding 20 remains
`present=1`; provenance remains `RECONCILE_PENDING`,
`discovery_reconciled=0`, `jellyfin_reconciled=NULL`; NAS title directory is
absent; Jellyfin exact GET count remains one. Delete gate is false, web is
healthy, writer READY, completion timer/service inactive, and
`teddy-discovery-jav-reconcile-apply.service` inactive. The separate
`teddy-discovery-jav-reconcile.timer` is active/waiting for a report-only
service; source routes it through `reconcile_remote`, emits `APPLY=0`, and does
not invoke apply. Its service is currently failed/not running; neither timer
nor service was started or changed in this checkpoint.

`DISCOVERY_CRASH_RECOVERY_HARDENED=YES`,
`WRITER_ERROR_LOGGING_HARDENED=YES`, and `RECOVERY_ELIGIBLE=YES`.
`DISCOVERY_RECONCILED=NO` intentionally: do not call `mark_absent` in this
checkpoint. Next is F2M-C3, applying only this exact operation's Discovery
reconciliation. Jellyfin remains a separate F2M-D step.

## Stage13-F2M-C3 — exact pending Discovery apply

The check-only helper remains read-only and reports one of two exact phases:
`READY_TO_MARK_ABSENT` requires the original present holding and no journal;
`WRITER_DONE_PROVENANCE_PENDING` requires `present=0` and the exact matching
operation journal. No unjournaled absent holding is treated as success.
The separate `deploy/stage13-f2m/reconcile_discovery_apply.py` acquires the
target title lock before the existing global JAV operation lock, rechecks the
operation while both are held, calls only the narrow Unix-socket writer,
verifies the exact Discovery row and journal, then conditionally changes only
the matching provenance `discovery_reconciled` flag. It has no NAS delete or
Jellyfin call path. Offline helper fixtures cover Phase A, crash recovery in
Phase B, missing/foreign journal refusal, title/global lock contention,
writer failure, post-writer verification failure, and provenance conflict.

For exact operation
`e8b5ba23-cb6d-4e5e-81f6-c1e5fdb79873` / VEMA-246 / holding 20, the fresh
production `--check-only` result immediately before apply was
`RECOVERY_ELIGIBLE=YES`, `RECOVERY_PHASE=READY_TO_MARK_ABSENT`. The apply helper
held both locks in title-then-global order and the writer returned
`RECONCILED`. Writer journal insertion and holding transition were atomic.
Read-only verification found holding 20 `present=0`, zero present VEMA-246
holdings, one exact matching journal row, and 183 current present JAV holdings.
The exact provenance operation is still `RECONCILE_PENDING`, with
`nas_delete_complete=1`, `discovery_reconciled=1`, `jellyfin_reconciled=NULL`,
four removed files / 2,844,317,586 bytes, and no remaining entries. Library's
Discovery-backed present-holdings projection now returns zero VEMA-246 rows.
No authenticated browser/API session was used for a UI request. Jellyfin was
not changed; its exact GET lookup still returns one item, intentionally pending
F2M-D. NAS title directory remains absent.

Production state remains gate=false, web healthy, writer service active and
host socket health `READY`; completion timer/service and reconcile-apply remain
inactive. The separate scheduled report-only reconcile timer remains
active/waiting and its paired report service is failed/not running; its source
uses the report path and emits `APPLY=0`, and neither unit was changed. During
this checkpoint the host writer socket was healthy, but the existing web
container's read-only bind directory did not show `writer.sock`; no web API was
used and no web recreate was performed. This does not affect the host-side
exact recovery just completed, but web-container writer connectivity should be
rechecked before any future delete flow.

`DISCOVERY_APPLY_HELPER_SAFE=YES`, `DISCOVERY_RECONCILED=YES`, and
`JELLYFIN_RECONCILED=NO` intentionally. This operation created exactly one
Discovery journal row and changed only holding 20 `present=1 -> 0` plus its
matching provenance discovery flag. NAS, Jellyfin, media state, completion,
Stage12, delete API, and new-operation counts remain untouched. Next is F2M-D:
reconcile only the exact stale Jellyfin item, then close the same provenance
operation to `COMMITTED` after exact verification.

## Stage13-F2M-D — previous exact Refresh attempt (PENDING)

Source commit `7a5d0d2` added exact path polling around a single item Refresh.
Production check-only found one VEMA-246 item; the helper sent one Refresh POST
and polled for 60 seconds, but the exact item remained. This historical attempt
is retained as evidence. It was not repeated in D2.

## Stage13-F2M-D2 — exact Deleted notification (PENDING)

Source commit `0fb6a59` adds `JellyfinClient.notify_deleted(media_path)`, using
the existing canonical `jellyfin_media_path(relative_path)` and the exact
`POST /Library/Media/Updated` payload with `UpdateType=Deleted`. The delete
reconciler now skips POST when exact count is zero, rejects more than one exact
path, and otherwise sends one Deleted notification then polls every 2 seconds
for at most 120 seconds. It no longer Refreshes items or requires an item ID.
Created notification behavior remains unchanged. Offline fixtures verify the
exact path/payload, one POST, initial absence, delayed disappearance, timeout,
ambiguity, malformed inventory, notification error, crash/re-run with zero
POST, and Created-vs-Deleted payloads.

The exact operation helper remains allowlisted to operation
`e8b5ba23-cb6d-4e5e-81f6-c1e5fdb79873` / VEMA-246. Check-only immediately before
apply returned `JELLYFIN_RECOVERY_ELIGIBLE=YES`, exact item count 1. Under the
per-title then global lock, the helper issued one exact Deleted notification
POST (no item Refresh POST and no Jellyfin item DELETE) and completed the
120-second bounded polling window. The exact item remained at count 1 after
polling, so no provenance finalization occurred and no further notification was
sent. Provenance remains `RECONCILE_PENDING`, `discovery_reconciled=1`,
`jellyfin_reconciled=NULL`.

Image `missav-dlp-web:stage13f2md2-0fb6a59` was built from source commit
`0fb6a59`; image ID is
`sha256:3187d0c7c5572d0b948199dd421bbe7bed2459efafdd295e020a6770be5d8814`.
Only `missav-dlp-web` was recreated with gate false. `/login` returned 200;
container restart count is zero; Discovery DB and writer socket mounts are RO,
title lock mount is RW, and NAS/Jellyfin secret mounts are present. Host and web
container writer health are READY, and the web socket remains visible after
this web recreation: `WEB_WRITER_SOCKET_VISIBLE=YES`. No writer restart
occurred, so socket restart durability is not proven:
`WEB_WRITER_SOCKET_DURABILITY_PROVEN=NO`.

Read-only final checks confirm holding 20 remains `present=0`, VEMA-246 present
count is zero, current JAV holdings are 183, and the exact NAS title directory
is absent. Jellyfin exact item count remains 1. Gate is false, web is healthy,
completion timer/service and reconcile-apply are inactive, and title/global
locks are free. No authenticated Library UI/API read was made in D2; the
Discovery present-holdings projection contains no VEMA-246 row.

`JELLYFIN_DELETED_NOTIFICATION=INCOMPLETE`, `JELLYFIN_RECONCILED=NO`,
`DELETE_OPERATION_FINAL=NO`, `CANARY_OPERATION_CLOSED=NO`, and
`STAGE13_CLOSE_READY=NO`. The current blocker is
`JELLYFIN_DELETED_NOTIFICATION_TIMEOUT_ITEM_STILL_PRESENT`. Do not send another
Deleted notification until a separate read-only investigation establishes why
the exact notification did not remove the stale item. The web writer socket's
restart durability remains a separate F2M-E verification.

## Stage13-F2M-D9 — durable Jellyfin notification contract (SOURCE ONLY)

The notifier uses `DURABLE_AT_MOST_ONCE`; exactly-once delivery cannot be made
atomic across a SQLite commit and an HTTP request. For a live exact Jellyfin
item, the reconciler first commits a row in
`library_delete_jellyfin_notification_attempts` inside the existing provenance
database, bound to operation ID, DVD ID, holding ID, source identity
fingerprint, manifest SHA-256, and Jellyfin item ID. It stores no media path.
Only a new claim permits one `UpdateType=Deleted` POST. An existing claim
prohibits another POST; retries perform GET-only verification. A crash after
claim but before POST, a POST timeout, or a POST exception with the item still
live remains pending as `JELLYFIN_NOTIFICATION_OUTCOME_UNKNOWN`. If the exact
item ID is absent, reconciliation can succeed. This preserves the unavoidable
uncertain crash window rather than risking a duplicate POST.

The ledger table is created lazily only by the transactional claim path. Read
checks and GET-only recovery do not create it. The claim transaction uses
`BEGIN IMMEDIATE`, revalidates the exact pending provenance row, and commits
before the network request. Normal delete, commit retry, reconcile endpoint,
and the exact-operation recovery helper use the same reconciler/claim contract.
Repository search finds only the reconciler's production `notify_deleted`
call; direct Created notification behavior remains unchanged.

Broad inventory path matches are candidates only. A single candidate must have
a non-empty ID and pass `/Items?Ids=...` verification with the same ID and
exact path. Exact-ID count zero is `BROAD_INVENTORY_GHOST`: success without a
claim or POST, even when that same old ID/path remains in broad inventory.
After a notification, polling uses the captured ID. A different live ID at
the same path fails closed as `JELLYFIN_PATH_REAPPEARED_DIFFERENT_ID`.

Offline D9 fixtures passed for broad absence, initial and post-removal ghosts,
claim-before-POST, crash before POST and after server acceptance, timeout and
exception retries, repeated apply, claim conflict, ambiguity, missing ID,
malformed/wrong-path exact-ID replies, different-ID re-addition, and unchanged
Created payload behavior. The ghost recovery-helper fixture committed only its
temporary provenance DB with zero POST and no ledger table creation. The
existing `teddy_library_delete_commit_smoke.py` regression could not start in
this workspace because neither `python3` nor `/opt/stage11-stt-venv/bin/python`
has Flask installed; no package was installed. Syntax compilation and
`git diff --check` passed. Production deploy, provenance finalization, Jellyfin
POST, NAS/Discovery mutation, restart, and gate change were all zero.

D9 leaves the production image and current VEMA provenance unchanged. D10 is
expected to deploy this source and, only after its production preconditions,
finalize VEMA-246 through the exact-ID ghost-aware path. The separate writer
socket restart-durability question remains for F2M-E.

### D9b — production-equivalent integration smoke follow-up

The earlier Flask limitation is resolved without installing packages: built
temporary image `missav-d9b-integration:6665ff8e` from clean source HEAD
`6665ff8e479ba404e99c6e4c53b02830e29abca5` using the repository Dockerfile.
Image ID:
`sha256:008ced8d484a599713a4fe184cd5dd6b173ad8f9d8542ab6726f6c56a6c5df1d`.
The Dockerfile build's Stage13 delete commit smoke also passed. In a separate
ephemeral container, the three required smokes passed with `--network none`, a
read-only container root, `/tmp` tmpfs only, and no host mounts or secrets:

- `teddy_library_delete_commit_smoke.py` — `Stage13-F1 offline delete commit safety smoke: OK`
- `teddy_library_delete_jellyfin_smoke.py` — `Stage13-F2M-D9 durable at-most-once Jellyfin smoke: OK`
- `deploy/stage13-f2m/reconcile_jellyfin_pending_smoke.py` — `Stage13-F2M-D9 ghost-aware Jellyfin recovery helper smoke: OK`

The existing integration fixture covered prepare/validate/commit, activity and
title-lock guards, Discovery writer preflight/reconcile boundaries, exact
manifest NAS mutation fixtures, provenance flow, and delete gate behavior.
All 3/3 required container smokes passed. The temporary image and ephemeral
container were removed after execution. Read-only post-check confirmed the
production web container remained on its prior image, running with gate=false,
`/login` 200 and restart count unchanged; completion and reconcile-apply units
remain inactive. No production service, database, NAS, Discovery, Jellyfin, or
gate mutation occurred.

`D9_DURABLE_NOTIFICATION_CONTRACT_VALIDATED=YES`
`INTEGRATION_SMOKE_PASS=YES`
`D10_DEPLOY_READY=YES` (source/integration validation only; production deploy
and VEMA finalization remain for D10 after its own preconditions).

## Stage13-F2M-D10 — deploy and close VEMA-246 canary

Preconditions passed at source HEAD
`52aa3f40f3bee3b70f62f859d71f8dfcf7e9ad07`, with validated source commit
`6665ff8e479ba404e99c6e4c53b02830e29abca5` in its ancestry, remote aligned,
and worktree clean. Before deploy, the exact VEMA provenance row was
`RECONCILE_PENDING` with NAS complete, Discovery reconciled, Jellyfin NULL,
four removed files / 2,844,317,586 bytes, empty remainder, and the expected
manifest digest. NAS title directory was absent; holding 20 and VEMA present
counts were zero; current JAV holdings were 183. Organizer and Stage12 activity
checks reported idle. Gate was false, production web was healthy, and
completion/reconcile-apply units were inactive.

Built the immutable local image from that HEAD with the existing Dockerfile:
`missav-dlp-web:stage13f2md10-52aa3f4`, image ID / SHA
`sha256:92104fcb5bf5c7501120b078ec0e8c778358f3b33064e77e4d89e0b6606274ff`.
All Dockerfile embedded checks passed, including the Stage13 delete commit,
D9 Jellyfin, and recovery-helper smokes. Rendered Compose config retained
gate=false, restart policy `unless-stopped`, and the existing title-lock bind.
Only `missav-dlp-web` was recreated with `--no-deps`; no writer or completion
service was restarted. Post-deploy the expected image is running, restart count
0, `/login` is 200, the environment digest and mount map match the prior
container, title-lock remains RW, writer socket is visible and health is READY,
and completion/reconcile-apply remain inactive. Writer socket restart
durability was not tested.

The deployed helper files' SHA-256 values matched the validated repository
source. Its production-configured check-only returned eligible YES with broad
exact-path count 1, candidate ID
`0fa5e1cd9743f9e30dc69054e1c12375`, exact-ID count 0, and
`BROAD_INVENTORY_GHOST`. The exact-operation apply returned
`JELLYFIN_APPLY=COMMITTED`, `DELETED_NOTIFICATION_POSTS=0`, and
`POLL_COMPLETE=True`. It finalized only the exact provenance transition; it
created no notification claim.

Read-only post-verification confirms provenance `COMMITTED`, NAS complete,
Discovery reconciled, Jellyfin reconciled, finish timestamp set, four files /
2,844,317,586 bytes removed, and empty remainder. The notification ledger has
zero rows for this operation. NAS title directory remains absent; holding 20
present=0; VEMA present=0; current JAV holdings=183. Jellyfin broad inventory
still returns the same old ID/path ghost, while exact-ID count is 0. No
user-scoped ID was available for an additional user-scoped GET. D10 Jellyfin
POST/Refresh/Scan/DELETE counts are all zero; NAS and Discovery writes are
zero. Completion remains intentionally inactive, so any newly downloaded
post-processing work stays queued for later.

`JELLYFIN_RECONCILED=YES`, `DELETE_OPERATION_FINAL=YES`, and
`CANARY_OPERATION_CLOSED=YES`. The broader Stage13 close remains pending:
`WEB_WRITER_SOCKET_DURABILITY_PROVEN=NO` and
`STAGE13_CLOSE_READY=NO`. Next checkpoint: F2M-E writer socket restart
durability only; do not resume completion until that checkpoint closes the
remaining Stage13 gate.

## Stage13-F2M-E1 — writer socket restart durability (FAIL)

Preconditions passed at HEAD `42578ee5df419aac38ddbbde4a6a24676513dd0a`,
with local and remote equal and a clean worktree. Production web was running on
the D10 image, `/login` returned 200, gate was false, completion and
reconcile-apply units were inactive, and writer service plus host/web health
were READY. The web container was not recreated during this checkpoint.

Effective writer unit `/etc/systemd/system/teddy-library-discovery-writer.service`
has no drop-ins. `ExecStart` runs
`/usr/bin/python3 /opt/missav-dlp-web/teddy-library-discovery-writer/releases/3daac14029ad049416373fa2c452a47a64c9b732/teddy_library_discovery_writer.py`
with the Discovery DB, provenance DB, and
`/run/teddy-library-discovery-writer/writer.sock` arguments. Effective values:
User=root, Group=teddy-library-discovery-writer,
RuntimeDirectory=teddy-library-discovery-writer,
RuntimeDirectoryMode=0750, RuntimeDirectoryPreserve=no, Restart=on-failure.
The web mount is a read-only bind from host
`/run/teddy-library-discovery-writer` to the same container path.

Before the single controlled writer restart, MainPID was `1184596`, NRestarts
0, host and web runtime-directory inode `135:1488725`, and host and web socket
inode `135:1488730`. The socket was a UNIX socket owned by `0:988`, mode 0660;
the runtime directory was owned by `0:988`, mode 0750. Host and web writer
health both returned READY.

After `systemctl restart teddy-library-discovery-writer.service`, MainPID is
`1357596`, NRestarts remains 0, service is active, and host runtime-directory
and socket inodes are `135:1511947` and `135:1511952`. The new host socket is
type socket, owner/group `0:988`, mode 0660, and host health is READY. The
existing web container ID is unchanged and its restart count remains 0. Its
runtime directory still has the old inode `135:1488725`; its socket is absent
(`WEB_SOCKET_DEV_INO_AFTER=ABSENT`) and a writer health request fails. `/login`
still returns 200 and gate remains false.

`HOST_RUNTIME_DIR_REPLACED=YES`, `HOST_SOCKET_REPLACED=YES`, and
`WEB_WRITER_SOCKET_VISIBLE_AFTER_RESTART=NO`.
`WEB_WRITER_HEALTH_AFTER_RESTART=FAIL`.
Classification: `RUNTIME_DIRECTORY_REPLACED_BIND_STALE`. systemd removed and
recreated the runtime directory while the existing directory bind remained
attached to the old inode. Web recreate/restart count is 0. No recovery or
web recreate was performed, so this remains a valid durability failure.

Read-only before/after comparison confirms the entire Discovery `holdings`
table checksum and reconcile-journal checksum are unchanged, holding 20 stays
present=0, VEMA present=0, current JAV holdings=183, and the exact committed
VEMA provenance row checksum is unchanged. Production data mutations,
Jellyfin/NAS changes, completion processing, and gate changes are zero; the
only production mutation was the authorized single writer-service restart.
Completion remains intentionally inactive, and new-download post-processing
remains pending.

`CANARY_OPERATION_CLOSED=YES`,
`WEB_WRITER_SOCKET_DURABILITY_PROVEN=NO`,
`STAGE13_CLOSE_READY=NO`. Next checkpoint E2: change the writer
RuntimeDirectory/bind persistence contract safely, then repeat the durability
proof. Do not resume completion before a passing proof.

## Stage13-F2M-E2 — runtime directory preserved, writer restart proof failed

Started from clean HEAD `bed69faaf93a0e186dd5cf535426570425574318`, with the
remote branch aligned. Production web was on the expected D10 image with
restart count 0, `/login` returned 200, delete gate was false, completion and
reconcile-apply units/timers were inactive, and the writer was active. The
E1 state was reproduced: host runtime directory/socket inodes were
`135:1511947` / `135:1511952`, while web retained the prior directory inode
`135:1488725` and had no socket; host writer health was READY and web health
failed.

The canonical repo-managed artifact is
`deploy/systemd/teddy-library-discovery-writer.service.d/10-runtime-directory-preserve.conf`:
`[Service] RuntimeDirectoryPreserve=restart`. It was installed as the matching
systemd drop-in and `daemon-reload` applied. Effective value is
`RuntimeDirectoryPreserve=restart`; the writer unit remains the existing
`/etc/systemd/system/teddy-library-discovery-writer.service` with
`RuntimeDirectory=teddy-library-discovery-writer`, mode 0750, root user,
`teddy-library-discovery-writer` group, and `Restart=on-failure`.

The stale web bind was recovered with exactly one web-only recreate using the
same immutable D10 image (`sha256:92104fcb5bf5c7501120b078ec0e8c778358f3b33064e77e4d89e0b6606274ff`),
`--no-deps`. Container ID changed once to `97b316c9ff44`; restart count is 0.
`/login` returned 200, gate remained false, title-lock remained a writable
bind, writer mount remained a read-only bind, and environment digest remained
`e76f155985392d403044f833e4ea9bd5276862a5102b5ba1ab2218fe6855b032`.
Before the proof restart, host and web runtime-directory inode were both
`135:1511947`; host and web socket inode were both `135:1511952`; host and web
health returned READY.

Exactly one explicit `systemctl restart teddy-library-discovery-writer.service`
was issued. The runtime-directory inode remained `135:1511947`, confirming the
new policy preserved the directory. However, the socket inode also remained
`135:1511952`: the previous socket pathname persisted. Writer startup failed
and systemd's `Restart=on-failure` generated 29 automatic failed starts
(`NRestarts=29`). The writer implementation's `_prepare_socket_parent()`
explicitly rejects an existing socket path and does not unlink it, so no new
socket was created. During these retries the unchanged web container still
saw the old socket inode, but connect/health failed. To stop the automatic
failure loop, the writer service was stopped once; systemd then cleaned the
host runtime directory/socket. No further restart, web recreate, or socket
unlink was attempted. Current writer service is inactive, the old web bind
still points at its prior directory inode, and web writer health is
unavailable. `/login` remains 200 and gate remains false.

`HOST_RUNTIME_DIR_PRESERVED=YES`, `HOST_SOCKET_RECREATED=NO`, and the required
proof failed with classification
`SOCKET_NOT_VISIBLE_THROUGH_PRESERVED_BIND` (the old path was visible briefly,
but it was not a new usable socket). Safe `preflight_holding` after the
restart returned `WRITER_UNAVAILABLE`; it performed no Discovery transition.

Read-only before/after checks match exactly: Discovery `holdings` has 184 rows
and SHA-256 `5ddc5494421d4e86a6f78bcd2268a408c5718f2e52a883fc0760090fecbcfacd`;
`library_delete_reconcile_journal` has 1 row and SHA-256
`d412d8ba7f773b0eaeeaa034ddc5705d138c32172bd729c9e38070444920e171`;
holding 20 remains absent, VEMA-246 present count is 0, JAV present holdings
remain 183. The exact VEMA provenance row remains COMMITTED with
`jellyfin_reconciled=1` and unchanged checksum
`d7c972131cd78d1c40b663b78d8cd886b638b17bdcc91aaeb9b55a96a6792ec6`.
Production Discovery content/schema, provenance, NAS, Jellyfin, delete
operation, completion, and gate mutations were zero. The only production
changes were the authorized drop-in install/daemon-reload, one web recreate,
one explicit writer restart, and one writer stop to halt systemd's automatic
failure loop.

`CANARY_OPERATION_CLOSED=YES`, but
`WEB_WRITER_SOCKET_DURABILITY_PROVEN=NO` and `STAGE13_CLOSE_READY=NO`.
Completion remains inactive. Next checkpoint must address the writer's
fail-closed stale socket startup behavior and its lifecycle safely; do not
resume completion until a successful proof shows the existing web bind sees a
new usable socket after one writer restart.

## Stage13-F2M-E3 — safe stale Unix socket reclaim

E2's frozen root cause is `STALE_SOCKET_STARTUP_REJECTED`: the effective
`RuntimeDirectoryPreserve=restart` keeps the runtime directory (and old socket
pathname) during a restart, while `_prepare_socket_parent()` rejected every
existing target. The `RuntimeDirectoryPreserve=restart` drop-in remains
installed and effective.

`teddy_library_discovery_writer.py` now reclaims an existing target only when
it is a real Unix socket and the bounded connect probe returns
`ECONNREFUSED`. A successful connect is treated as an active listener and
fails closed. `ENOENT` proceeds only after a second check confirms the target
is absent. `EACCES`, timeout, `EAGAIN`, and all other results fail closed. A
symlink, regular file, directory, or other non-socket is rejected without
unlink. Before unlink, the code rechecks that the parent remains the same real
directory and that the socket remains the same device/inode/type/uid/gid and
is owned by the service euid. It then pins the parent with an `O_NOFOLLOW`
dirfd, checks the parent and exact basename again relative to that fd, and
unlinks only that single socket pathname. The writer then binds the same path
with the existing 0660 socket mode; the parent remains 0750. No glob or
recursive cleanup is used.

The expanded `teddy_library_discovery_writer_smoke.py` covers absent path,
regular file, symlink and symlink parent, directory at socket path, active
listener preservation/usability, stale socket reclaim, restart simulation,
ENOENT disappearance, inconclusive connect errors, socket replacement race,
and parent replacement race. In the restart fixture, the parent inode stays
the same, the new socket gets a different inode, health returns READY, and
Discovery fixture rows/journal remain unchanged across restart and health.
The replacement-race fixture confirms a new active socket is not unlinked.

Regression smokes passed 8/8 in an ephemeral container using the existing
production-equivalent D10 image
`missav-dlp-web:stage13f2md10-52aa3f4`
(image ID `sha256:92104fcb5bf5c7501120b078ec0e8c778358f3b33064e77e4d89e0b6606274ff`).
The repo was a read-only bind, network was disabled, root filesystem was
read-only, and only `/tmp` was writable. Passed:

- `teddy_library_discovery_writer_smoke.py`
- `teddy_library_delete_dryrun_smoke.py`
- `teddy_library_delete_commit_smoke.py`
- `teddy_library_delete_activity_smoke.py`
- `teddy_library_delete_jellyfin_smoke.py`
- `reconcile_discovery_pending_smoke.py`
- `reconcile_discovery_apply_smoke.py`
- `reconcile_jellyfin_pending_smoke.py`

Production writer was not started or restarted; it remains inactive, with
`RuntimeDirectoryPreserve=restart` effective and host runtime directory still
absent from the E2 stop. Production web was not recreated and remains on its
D10 image; `/login` is 200 and gate remains false. Completion and
reconcile-apply remain inactive. No production source install, writer start,
Discovery/provenance write, NAS/Jellyfin mutation, completion, or gate change
occurred.

`ACTIVE_SOCKET_UNLINK_POSSIBLE=NO`, `NON_SOCKET_UNLINK_POSSIBLE=NO`, and
`TOCTOU_IDENTITY_RECHECK=YES`. Next checkpoint E4: deploy the validated writer
source, start the production writer once, and repeat the web-bind durability
proof. Until then writer connectivity remains unavailable and completion stays
inactive.

## Stage13-F2M-E4 — E3 release installed; durability proof incomplete

Preconditions passed at clean, remote-aligned HEAD
`d9e04acfe6492635ea45922ee3f65f169c5d9437`: web `/login` was 200, the D10
image was running with gate=false, completion/reconcile-apply were inactive,
writer was inactive, and the host writer runtime directory was absent. VEMA-246
provenance was COMMITTED; holding 20 present=0 and VEMA-246 present=0.
Before/after read-only checks match: Discovery `holdings` has 184 rows and
SHA-256 `5ddc5494421d4e86a6f78bcd2268a408c5718f2e52a883fc0760090fecbcfacd`;
`library_delete_reconcile_journal` has 1 row and SHA-256
`d412d8ba7f773b0eaeeaa034ddc5705d138c32172bd729c9e38070444920e171`; the
exact COMMITTED VEMA provenance row SHA-256 is
`d7c972131cd78d1c40b663b78d8cd886b638b17bdcc91aaeb9b55a96a6792ec6`.

Installed the validated E3 writer and its five import dependencies from exact
source commit `d9e04acfe6492635ea45922ee3f65f169c5d9437` into
`/opt/missav-dlp-web/teddy-library-discovery-writer/releases/d9e04acfe6492635ea45922ee3f65f169c5d9437/`.
The release has a matching `SOURCE_COMMIT`, `SHA256SUMS` verified for all six
Python files, root:root ownership, files mode 0444, and release directory mode
0555. The writer source SHA-256 is
`8898087c4830a6e2729c5593377224a9cfa518147aa0ec40bdc554cba392410e`;
imports were verified with host Python without writing bytecode.

Added and installed repo-managed drop-in
`deploy/systemd/teddy-library-discovery-writer.service.d/20-execstart-d9e04ac.conf`.
After `daemon-reload`, effective ExecStart points to the new release and
retains the same Discovery DB, provenance DB, socket, root user, service group,
RuntimeDirectory and mode, and `Restart=on-failure`. The E3
`RuntimeDirectoryPreserve=restart` drop-in remains effective.

One writer `systemctl start` was issued at 23:56:33 KST. Its first status sample
showed an active process (PID 1374809), but no socket yet. The monitor compared
new activation `NRestarts=0` to the prior E2 value 29 and incorrectly treated
the reset as an automatic restart. It then issued the bounded stop before a
proper readiness wait. Journal shows only Started then Stopping/Stopped, with
no writer startup error and no automatic restart event. The stop ended with
SIGTERM; host runtime directory was cleaned. Current writer service is
inactive, `NRestarts=0` for that activation, and the service has not been
started again. Therefore initial start/host health is **unverified**, not a
confirmed release failure.

Because readiness was not verified, web recovery recreate was not attempted.
Web remains container `97b316c9ff44` on the D10 image with restart count 0;
`/login` remains 200 and gate=false. No post-recreate inode baseline, writer
preflight, writer durability restart, or web-after-restart proof was performed.
Host runtime directory is currently absent and writer connectivity remains
unavailable. Completion and reconcile-apply remain inactive.

Discovery holdings, reconcile journal, and exact VEMA provenance checksums are
unchanged. No Discovery content/schema, provenance, NAS, Jellyfin, delete,
completion, or gate mutation occurred. Production changes were limited to the
validated immutable writer release install, service ExecStart drop-in install
and daemon-reload, one writer start, and one bounded writer stop.

`CANARY_OPERATION_CLOSED=YES`; `WEB_WRITER_SOCKET_DURABILITY_PROVEN=NO` and
`STAGE13_CLOSE_READY=NO`. E4 is `INCOMPLETE`. Next checkpoint must retry the
runtime proof only after authorization, using the new activation's restart
counter baseline (zero) and waiting boundedly for the socket/host health before
any web recreate. Keep completion inactive until a full successful E4 proof.

## Stage13-F2M-E4b — writer readiness and durability proof PASS

E4's early stop came from comparing the new activation's reset
`NRestarts=0` against E2's historical value 29. That was a monitor error; the
E4 journal showed no writer startup error or automatic restart. E4b uses the
new activation's current counter as the baseline and waits for bounded socket
health before proceeding.

Preconditions passed at HEAD `cb3a15f9222b29159da925bd741756897fd24dcc`:
local/remote aligned and worktree clean; writer inactive; host runtime
directory absent; effective ExecStart pointed to the E3 release;
`RuntimeDirectoryPreserve=restart`; web `/login` 200 and gate false;
completion/reconcile-apply inactive. VEMA provenance was COMMITTED, holding 20
present=0, VEMA present=0. Baseline Discovery checksums were holdings 184 rows
`5ddc5494421d4e86a6f78bcd2268a408c5718f2e52a883fc0760090fecbcfacd`, journal
1 row `d412d8ba7f773b0eaeeaa034ddc5705d138c32172bd729c9e38070444920e171`, and
VEMA provenance `d7c972131cd78d1c40b663b78d8cd886b638b17bdcc91aaeb9b55a96a6792ec6`.

The installed immutable release is
`/opt/missav-dlp-web/teddy-library-discovery-writer/releases/d9e04acfe6492635ea45922ee3f65f169c5d9437/`, with exact E3 source marker and
all source hashes verified. Effective unit retains root user, service group,
canonical Discovery/provenance/socket arguments, `Restart=on-failure`,
and `RuntimeDirectoryPreserve=restart`; service is enabled.

Writer start was issued once. `NEW_ACTIVATION_NRESTARTS_BASELINE=0`; within the
15-second bound the service was active with PID 1551593, `NRestarts=0`, and
host health READY. Runtime dir/socket were mode 0750/0660, owner/group 0:988.

The D10 web container was recreated exactly once with `--no-deps` to recover
the stale bind. It remains on image
`missav-dlp-web:stage13f2md10-52aa3f4`, image SHA
`sha256:92104fcb5bf5c7501120b078ec0e8c778358f3b33064e77e4d89e0b6606274ff`;
its new container ID is `e7d8e64a05c6158e2ed8c3d60478281b316d6b75e8a2ec99095ab0a4cebb1c80`,
restart count 0. `/login` returned 200, gate=false, title-lock remains RW,
and writer bind remains RO. Environment digest matches prior deployment.

Before the proof restart, host and web runtime-directory inode were both
`135:1531262`; host and web socket inode were both `135:1531267`. The same
valid present JAV holding (ID 1, `FC2-PPV-4592689`) returned READY from
`preflight_holding`; holding identity was unchanged and no mark-absent was
called.

Immediately before the single proof restart, MainPID was 1551593 and
`PROOF_NRESTARTS_BASELINE=0`. After restart MainPID changed to 1552535,
`NRestarts` remained 0, and host health returned READY. Host runtime-directory
inode stayed `135:1531262`; host socket inode changed to `135:1531387`.

The web container was not recreated or restarted after the proof restart. Its
runtime-directory inode remained `135:1531262`, and its socket inode became
`135:1531387`, matching the host's new socket. Socket type and owner/group/mode
remain correct; web health returned READY. The same safe holding preflight
returned READY again.

After both preflights and the restart, Discovery holdings/journal and VEMA
provenance checksums remained exactly equal to baseline. Holding 20 remains
present=0, VEMA present=0, and current JAV holdings=183. No Discovery content
or schema, provenance, NAS, Jellyfin, delete, completion, or gate mutation
occurred. Production operations were limited to the already installed
immutable release and unit configuration, one writer start, one stale-bind
web recreate, and one writer restart.

`CANARY_OPERATION_CLOSED=YES`, `WEB_WRITER_SOCKET_DURABILITY_PROVEN=YES`, and
`STAGE13_CLOSE_READY=YES`. Completion and reconcile-apply remain inactive by
intent. Next checkpoint E5: close Stage13 and separately resume completion to
process pending post-download work and confirm NAS organization/Jellyfin
registration.

## Stage13-F2M-E5 — Stage13 closed; completion resumed, Jellyfin pending

At HEAD `e84c669581260090fa2acc7aaeed70b244337594`, the Stage13 file-manager
and delete scope is closed: `STAGE13_STATUS=CLOSED`,
`STAGE13_RESULT=PASS`, `CANARY_OPERATION_CLOSED=YES`,
`WEB_WRITER_SOCKET_DURABILITY_PROVEN=YES`, and `STAGE13_CLOSE_READY=YES`.
The VEMA-246 operation remains COMMITTED (NAS, Discovery, and Jellyfin flags
all set); holding 20 remains absent. The delete gate stayed false.

Before completion resumed, the pinned systemd wrapper still selected runtime
`705bf9e700156d88523babfad15861a5faee9ff2`, with
`TEDDY_TITLE_LOCK_DIR=/opt/missav-dlp-web/title-locks`. The timer and service
were inactive and the reconcile-apply service was inactive. The read-only
completion planner found 34 downloads, one eligible organizer candidate
(`HMN-904`), and 33 held candidates. Organizer active count was zero. Media
jobs were COMPLETED=34, PENDING=19, FAILED=1, RUNNING=0. The sole failed row,
MFCS-085 / job 174261, was FAILED at attempt 17161 and EXHAUSTED, so it was not
retry eligible. Stage12 had no RUNNING or GENERATED rows; its counts were
PUBLISHED=163 and UNRESOLVED=10. JAV present holdings were 183.

The pinned `teddy-completion-stage9.service` was manually started once before
the timer. It ran 2026-09-30 08:16:10–08:16:31 KST and exited 0. Its result was
total=34, eligible=1, held=33, applied=1. HMN-904 completed organizer job 185:
the exact source file was removed from the downloads root and the canonical
NAS file `HMN/HMN-904/HMN-904.mp4` was created as a regular file, size
3,315,951,470 bytes. Discovery holding 185 is present=1 with the same path,
size, and mtime; parse status is MATCHED. The media stage reconciled one job
and completed NOSKN-104 (attempted=1, completed=1, failed=0); metadata recovery
recovered MARR-014 (attempted=1, failed=0). NOSKN-104 has one exact live
Jellyfin path match at `/media/adult/NOSKN/NOSKN-104/NOSKN-104.mp4`.

Only after the successful manual service run, the completion timer was
enabled and started with `systemctl enable --now` at 08:19:36 KST. It became
active/waiting with its first elapse 60 seconds later; an 8-second observation
found the service inactive and no immediate trigger. Subsequent service runs
followed the timer schedule and exited 0. By the 08:48 KST snapshot, organizer
jobs for 21 titles had completed, including HMN-904; JAV present holdings were
204. There were no duplicate present DVD IDs, parse mismatches, active
organizer jobs, or RUNNING media jobs. Current media counts were
COMPLETED=40, FAILED=16, PENDING=19, RUNNING=0. MFCS-085 remains FAILED at
attempt 17161 and was not rerun. Other pending-media failures entered their
configured backoff; the timer did not issue immediate retries.

The timer advanced HMN-904's pending media job 1386103, but that job failed
once at attempt 1 with a connection reset while fetching media metadata. The
job is now FAILED and subject to the configured one-hour backoff. A bounded
GET-only Jellyfin inventory check found zero exact-path items for HMN-904 and
for the 21 newly organized titles in the snapshot. No manual Jellyfin refresh
or scan was sent. The exact HMN-904 canonical NAS file and matching Discovery
holding remain present, but Jellyfin registration is not verified.

At the final runtime check, web `/login` returned 200, delete gate=false,
writer host/web health was READY, writer remained active/enabled,
Stage12 RUNNING/GENERATED remained zero, reconcile-apply was inactive, the
completion service was inactive, and the completion timer was enabled and
active/waiting with its next elapse in the future. Thus
`COMPLETION_TIMER_RESUMED=YES`. This E5 checkpoint remains INCOMPLETE because
Jellyfin did not register HMN-904; the bounded media job failed with a network
connection reset. The timer remains on its normal schedule, and HMN-904 is
protected by media retry backoff. No additional manual service run or
Jellyfin mutation was made. Follow-up should inspect the metadata-fetch
connection failure and verify the exact HMN-904 Jellyfin path after the
existing retry policy permits another attempt.

Follow-up snapshot at 2026-09-30 08:50:55 KST: normal timer processing had
organized 24 newly present completion-stage9 titles, bringing current JAV
holdings to 207 unique IDs. A complete Jellyfin inventory GET still returned
zero exact path matches for those 24 titles, including HMN-904. Media state
was COMPLETED=40, FAILED=19, PENDING=19, RUNNING=0; MFCS-085 stayed at
attempt 17161 and HMN-904 stayed FAILED at attempt 1. The timer was enabled
and active/waiting with next elapse 08:51:48 KST; service was inactive after
its latest exit 0. The E5 Jellyfin-registration blocker remains open while
the timer continues its normal schedule.

## Post-Stage13 Media-F1 — metadata fetch failure forensic

At source HEAD `5c3269d1f86e0d4c7434b0911e43d4aa01315a30`, the completion timer
was stopped once and left enabled but inactive to prevent additional media
attempts. At the end of the checkpoint, `teddy-completion-stage9.timer` and
`teddy-completion-stage9.service` were both inactive; the writer remained
active and host/web READY, the delete gate remained false, and
reconcile-apply remained inactive. Stage13 remains CLOSED/PASS with the
canary closed and writer socket durability proven.

The read-only media DB snapshot was COMPLETED=40, FAILED=37, PENDING=11,
RUNNING=0. In the 34-title recent completion-stage9 cohort, 23 jobs were
FAILED at attempt 1 and 11 were PENDING at attempt 0. Recent failure classes
were CONNECTION_RESET=20 and COVER_URL_MISSING=3. Across all failed jobs the
corresponding counts were CONNECTION_RESET=31 and COVER_URL_MISSING=6.
MFCS-085 remains exhausted and is not eligible for automatic retry.

HMN-904 job 1386103 is FAILED at attempt 1, updated
`2026-09-29T23:45:35+00:00`, with a connection reset. Its stored cover host is
`www.javdatabase.com`; the URL itself is intentionally omitted. The pinned
runtime pipeline calls `build_media_bundle()` before `publish_bundle()`,
`resolve_library()`, and `notify_created()`. `build_media_bundle()` fetches
the poster through urllib before returning the bundle. Therefore HMN-904
failed at `MEDIA_FAILURE_STAGE=POSTER_FETCH`, before sidecar publish and before
any Jellyfin call. Its exact canonical title directory contains the MP4 but
no NFO or poster, matching this pre-publish failure. The same MP4-only state
was confirmed for bounded comparison titles MARR-014 and MAAN-945; MAAN-945
was classified COVER_URL_MISSING.

Jellyfin GET-only correlation found all 23 recent FAILED titles and all 11
PENDING titles at exact item count 0. The six recent COMPLETED titles
NOSKN-104, MILK-306, STSK-242, NHDTC-247, NHDTC-250, and STSK-243 each had
one exact Jellyfin item. No recent COMPLETED title was missing from Jellyfin,
so these observations point to a pre-notification media failure rather than
a Jellyfin registration failure.

From the production completion host namespace, a bounded probe of the stored
HMN-904 cover URL (hostname only retained) returned DNS_OK=YES and TCP_OK=YES,
but TLS_OK=NO with `ConnectionResetError`/errno 104. The same urllib stack
returned URL_OPEN_OK=NO with `URLError` caused by `ConnectionResetError`.
The systemd completion service has no proxy environment or EnvironmentFiles;
the host manager and interactive environment also expose no proxy variables.
Together with repeated resets across recent titles, classify this as
`SYSTEMIC_METADATA_FETCH_CONNECTIVITY_FAILURE` on the observed cover-fetch
route, with a separate COVER_URL_MISSING subset. No media retry, source
change, Jellyfin request, or Discovery/provenance/NAS data write was made.
The only production runtime change was the requested timer stop.

Next checkpoint: diagnose the outbound TLS reset/route for
`www.javdatabase.com` and decide on retry policy before resuming the timer.
Do not manually retry HMN-904 until that decision; MFCS-085 remains excluded.

## Post-Stage13 Media-F2 — direct vs Gluetun TLS route forensic

At expected HEAD `a15738bc74c85112de78f50943457a494a0d7367`, the completion
timer and service remained inactive; the timer remained enabled. Writer
service remained active. Stage13 remains CLOSED/PASS. Probes used the exact
HMN-904 stored cover URL from the Discovery DB, but only the `https` scheme
and `www.javdatabase.com` hostname were retained in output.

The host general TLS control to `example.com` passed DNS, TCP/443, TLS 1.3,
and HTTPS GET (200), so general host TLS was healthy. HMN-904 host resolution
returned four addresses (two IPv4 and two IPv6). On the host direct route,
Python urllib failed with `ConnectionResetError` errno 104; `curl -4` exited
35 with HTTP 000; and `openssl s_client` with SNI also observed a reset.

The existing `missav-dlp-web` container was probed in place, with proxy
handling explicitly disabled for the direct comparison. Its direct urllib
request also failed with `ConnectionResetError` errno 104. The existing
`GLUETUN_PROXY_URL` was read without printing its raw value and resolved to
the expected logical target `http://gluetun:8888`. The proxy was reachable;
Python urllib HTTPS CONNECT/open through it succeeded with HTTP 200 and
`Content-Type: image/webp`, and a one-byte read succeeded. No second title
was probed.

Classification: `DIRECT_EGRESS_BLOCKED_OR_RESET_PROXY_ROUTE_OK`. The result
shows that both host and web-container direct routes reset this target while
the existing Gluetun proxy route succeeds; this is consistent with a direct
egress route/IP-path issue and does not establish that the target itself
blocks all clients. `COVER_URL_MISSING` remains a separate metadata quality
class. No service/timer start, media retry, source/config change, container
restart/recreate, Jellyfin operation, or media/Discovery/NAS/provenance write
occurred. Production mutation count was zero. The timer remains stopped.

Next checkpoint: design and validate a bounded production completion poster
fetch route using the existing Gluetun proxy, preserving fail-closed behavior
and leaving media jobs untouched until an explicit controlled retry plan.

## Post-Stage13 Media-F3 — bounded poster-only Gluetun proxy support

F3 source work started at `932bf88c197cc0ec1237788babae05f39a971f1f`. The
previous direct-vs-proxy evidence remains: host and web-container direct TLS
to `www.javdatabase.com` reset, while the Gluetun HTTP proxy fetch succeeded.
Stage13 remains CLOSED/PASS. During F3 the completion timer stayed enabled
but inactive, the completion service stayed inactive, the delete gate stayed
false, and writer host/web health returned READY. Web `/login` returned 200.

Poster fetching now has an explicit `--media-poster-proxy-url` runner option.
The runner creates one poster fetcher and passes it only through
`run_media_pipeline(..., fetcher=...)` to `build_media_bundle()` and
`fetch_poster()`. Jellyfin receives no proxy setting; SSH/NAS code is
unchanged. No global HTTP_PROXY/HTTPS_PROXY/ALL_PROXY value is read or set,
and no process-wide urllib opener is installed. Unset configuration keeps
the existing direct urllib fetch behavior. Configured proxy requests use a
local opener only; the explicit proxy handler ignores urllib's `no_proxy`
bypass so a configured request cannot silently go direct. Proxy/CONNECT
errors propagate with no fallback and no added fetch retry.

Proxy validation accepts only `http://127.0.0.1:<explicit-port>` (optionally
with a root slash); it rejects non-loopback and remote hosts, other schemes,
credentials, missing/invalid ports, paths, queries, and fragments. The
existing User-Agent, Accept header, 20-second timeout, bounded poster read,
content-type/format checks, and 25 MiB size limit are unchanged. Missing
cover URLs still fail as `COVER_URL_MISSING` before any fetch.

The running Gluetun container already had host mapping
`127.0.0.1:58888 -> container:8888`; container inspection confirmed it is
loopback-only. The repository Gluetun Compose source now records the same
`127.0.0.1:58888:8888/tcp` mapping. This source edit was not applied to
production. The F4 host-runner value is
`--media-poster-proxy-url http://127.0.0.1:58888`.

Offline checks passed under `/usr/bin/python3` 3.13.5, the same interpreter
used by the current completion wrapper: media metadata, media pipeline,
media jobs, completion runner, completion orchestrator, completion-media,
and title-lock smokes; Python compilation; and Compose config validation in
a temporary directory with a placeholder empty `gluetun.env`. The poster
smoke includes a local HTTP CONNECT proxy fixture, verifies direct mode and
proxy headers/timeout, forces proxy failure without direct fallback, checks
malformed proxy validation before opener/network construction, checks
missing-cover behavior, and preserves format/size validation.

F3 made source and offline-test changes only. Production image/release and
Compose were not applied; timer/service were not started; no media job or
Discovery/provenance/NAS/Jellyfin data was changed; no retry was run.

F4 plan: confirm the host loopback proxy endpoint with a bounded probe; install
the validated immutable completion runtime; pass only
`--media-poster-proxy-url http://127.0.0.1:58888` from the host wrapper; keep
the timer stopped; perform one controlled HMN-904 retry; verify poster/NFO
publish and the exact Jellyfin item; then decide whether to resume the timer.

## Post-Stage13 Media-F3b — exact one-title media retry selector

F3b source work started at `a09abec545419954aa4a06b6a0dcd4d186cc66a0`.
`run_retryable_media_jobs()` now accepts `target_dvd_id`; unset preserves the
existing ordered generic behavior. A supplied ID is normalized with the
existing canonical DVD-ID regex and read by exact uppercase ID before
eligibility calculation. Only that row can be evaluated, locked, marked
RUNNING, attempted, or finalized. Missing targets return `TARGET_NOT_FOUND`
without generic fallback. Backoff, max attempts, stale-running, title-lock,
and conditional state-recheck rules remain in force; a held target never
falls through to another eligible job.

The runner adds `--media-target-dvd-id` and explicit `--media-only` mode.
Media-only requires `--apply`, an exact target, media DB/lock, Jellyfin
configuration, and the poster-only `--media-poster-proxy-url`. It skips the
download listing/planner, organizer processor, media-job reconciliation, and
metadata recovery, then invokes the media runner once with the exact target.
This keeps unrelated newly downloaded titles out of the controlled retry.
The poster fetcher continues through the existing poster-only injection point;
Jellyfin and NAS/SSH interfaces receive no proxy configuration.

Offline selector fixtures passed: unset ordering, exact eligible target,
backoff hold, exhausted target, missing target/no fallback, invalid target
before DB/lock creation, invalid timestamp hold, busy title lock, successful
target attempt, and failed target attempt. Runner fixtures confirm media-only
skips planner/organizer/reconcile/metadata recovery, forwards HMN-904 as the
only media target, retains the poster fetcher injection, and rejects
media-only CLI use without proxy configuration before creating an SSH
client. Existing retry policy and lock-race fixtures still pass.

The full requested regression set also passed: media jobs, completion runner,
media metadata (including proxy fail-closed and COVER_URL_MISSING), media
pipeline, completion-media, completion orchestrator, title-lock, and Python
compilation.

F3b changed source and offline tests only. No production release/wrapper or
Compose was applied; completion timer/service remained stopped; no media
retry or media DB, Discovery, provenance, NAS, or Jellyfin mutation occurred.
Stage13 remains CLOSED/PASS. HMN-904 controlled retry is not yet performed.

F4 plan: bounded-probe the existing host loopback proxy; install the
immutable F3/F3b completion release; while the timer remains stopped, invoke
the existing wrapper with `--apply`,
`--media-only --media-target-dvd-id HMN-904 --media-max-items 1`, and
`--media-poster-proxy-url http://127.0.0.1:58888`. The selector must report
normal backoff/exhaustion holds without bypass. If eligible, permit exactly
that one media attempt, verify NFO/poster publish and exact Jellyfin item,
then decide whether to resume the timer.

## Post-Stage13 Media-F4 — exact HMN-904 proxy retry; Jellyfin item not visible (INCOMPLETE)

At source HEAD `496043fcd03655b893584f9803f5aaba926a3ff3`, the completion timer
was enabled but inactive; the completion service and reconcile-apply were
inactive. The writer service was active and host/web health returned READY;
web `/login` returned 200, delete gate was false, and the web container stayed
on image `missav-dlp-web:stage13f2md10-52aa3f4` with restart count 0. Stage13
remains CLOSED/PASS. No completion service, timer, web, or writer restart was
performed.

Before applying the retry, the wrapper pointed at pinned runtime
`705bf9e700156d88523babfad15861a5faee9ff2`. Its existing DB, media DB, writer
locks, NAS SSH key/known-host paths, Jellyfin URL/key path, library paths, and
title-lock root were retained. HMN-904 media job 1386103 was `FAILED`,
attempt 1, and the source `retry_eligibility()` returned `ELIGIBLE` under the
existing max-attempt/backoff/stale-running policy. MFCS-085 remained `FAILED`,
attempt 17161, `EXHAUSTED`. HMN-904 Discovery holding 185 was present and
matched `HMN/HMN-904/HMN-904.mp4`, size 3,315,951,470 bytes. The exact NAS
title directory contained only that MP4; NFO and poster were absent. Jellyfin
GET-only exact-path count was 0.

The host mapping is loopback-only: `127.0.0.1:58888 -> Gluetun:8888`. A
bounded request to the stored cover host `www.javdatabase.com` through that
proxy returned HTTP 200, `image/webp`, and a 64-byte read:
`POSTER_PROXY_READY=YES`.

Installed immutable runtime
`/opt/missav-dlp-web/stage9-runtime/releases/496043fcd03655b893584f9803f5aaba926a3ff3`
from exact source commit `496043fcd03655b893584f9803f5aaba926a3ff3`. It reuses
the prior 24-module runtime closure; all 24 file SHA-256 hashes matched the
repo blobs, the source marker is exact, the release is root-owned/read-only,
and host Python compiled the closure and imported the runner successfully.
The normal completion wrapper was backed up to
`/opt/missav-dlp-web/backups/stage9-f4-20260930-111424/teddy-completion-stage9-runner`
and atomically switched to this release. `bash -n` passed. The wrapper keeps
the existing arguments and title-lock root, adds only
`--media-poster-proxy-url http://127.0.0.1:58888`, and sets no global proxy
environment variables. The timer remained stopped.

Immediately before execution, HMN-904 remained `ELIGIBLE`; a deterministic
safe-field digest covered all 88 media rows. The exact media-only command
used `--apply --media-only --media-target-dvd-id HMN-904 --media-max-items 1`
with the production DB/NAS/Jellyfin configuration and poster proxy. It ran
directly from the immutable runtime, not through systemd. Result:
`attempted=1`, `completed=1`, `failed=0`; HMN-904 moved from `FAILED / 1` to
`COMPLETED / 2`. Organizer, media reconciliation, and metadata recovery were
skipped. Comparing every non-HMN media row's job ID, DVD-ID, status, attempt
count, and updated time found zero changes. MFCS-085 remained unchanged. The
Discovery holding identity also remained unchanged.

The exact NAS directory now contains the original MP4 at the same size,
one `HMN-904.nfo` (793 bytes), and exactly one poster, `poster.webp` (10,128
bytes), with zero temp/partial files. The pipeline completed its normal
Created-notification path; no manual Jellyfin refresh, scan, or notification
was sent. Jellyfin exact-path GET polling ran every 2 seconds for the full
120-second bound (60 polls) and still returned count 0. Classification:
`MEDIA_JOB_COMPLETED_BUT_JELLYFIN_NOT_VISIBLE`. No second retry or Jellyfin
mutation is authorized by this result.

The production completion timer remains enabled but inactive; service and
reconcile-apply remain inactive. Writer remains active with host/web READY,
web login remains 200, and the gate remains false. Production changes were
limited to the immutable runtime install, wrapper backup/atomic update, the
single HMN-904 media attempt and state transition, the NFO/poster publish, and
the pipeline's normal Created notification. Unrelated media rows, Discovery
identity, and HMN-904 MP4 were unchanged. No delete/provenance, broad NAS,
manual Jellyfin, or timer operation occurred.

`POSTER_PROXY_PRODUCTION_VALIDATED=YES` for the poster fetch and sidecar
publish. `HMN904_CONTROLLED_RETRY=INCOMPLETE` because Jellyfin did not expose
the exact item within 120 seconds. Next F5 must investigate the normal Created
notification/library registration path and define the remaining failed/pending
cohort policy. Keep the completion timer stopped; do not retry HMN-904 or send
another Jellyfin notification/refresh/scan until separately authorized.

## Post-Stage13 Media-F5 — Created notification reached HMN parent refresh; no Movie indexed (READ-ONLY)

Preconditions passed at HEAD `c4cc82a0c6aaaa5f1c9e92393b494865f6cb64a5`,
with local and remote equal and a clean worktree. The completion timer remained
enabled but inactive, completion and reconcile-apply services were inactive,
writer remained active/host+web READY, `/login` returned 200, and the delete
gate remained false. Stage13 remains CLOSED/PASS. HMN-904 is still
`COMPLETED / attempt=2`; its Discovery holding 185 remains present=1 at
`HMN/HMN-904/HMN-904.mp4`, size 3,315,951,470 bytes. NAS exact-title contents
are the MP4 (3,315,951,470 bytes), `HMN-904.nfo` (793 bytes), and
`poster.webp` (10,128 bytes). Jellyfin exact Movie path count remains 0.
MFCS-085 remains `FAILED / attempt=17161 / EXHAUSTED`.

Jellyfin GET `/System/Info` returned version `10.11.11`. In the tagged
[v10.11.11 LibraryController](https://github.com/jellyfin/jellyfin/blob/v10.11.11/Jellyfin.Api/Controllers/LibraryController.cs),
`POST /Library/Media/Updated` iterates `dto.Updates` and passes each `item.Path`
to `ReportFileSystemChanged`; the controller does not branch on `UpdateType`.
The F4 pipeline returned complete, and its `JellyfinClient` treats any
non-2xx response as an error, so the Created request reached the client-side
success path (the actual HTTP status was not persisted). The success therefore
means notification accepted, not item indexed.

The F4 media row `updated_at=2026-09-30T02:15:36+00:00` anchors the notify
window at approximately 11:15:36 KST. The bounded log window was
11:12:36–11:18:36 KST (02:12:36–02:18:36 UTC). GET `/System/Logs` returned
200 and listed `log_20260930.log`; its bounded relevant result was:
`[2026-09-30 02:16:36.958 +00:00] [INF] ... LibraryMonitor: "HMN"
("/media/adult/HMN") will be refreshed.` No `New file refresher created`
message or error/exception appeared in that window. The explicit creation log
is therefore `REFRESHER_CREATED_EVIDENCE=UNKNOWN`; the `will be refreshed`
message proves the timer callback reached the refresh target, so
`REFRESH_EXECUTED_EVIDENCE=YES`, with
`REFRESH_TARGET_PATH=/media/adult/HMN` and
`REFRESH_ERROR_EVIDENCE=NO` in the checked window. Notification evidence is
`NOTIFICATION_RECEIVED_EVIDENCE=YES` from the pipeline's 2xx-success path and
the resulting LibraryMonitor record.

The tagged [v10.11.11 FileRefresher source](https://github.com/jellyfin/jellyfin/blob/v10.11.11/Emby.Server.Implementations/IO/FileRefresher.cs)
sets its one-shot timer from `LibraryMonitorDelay`, resolves the changed path
with `FindByPath` while ascending parent paths, logs the item that will be
refreshed, then calls `ChangedExternally()`. The tagged
[LibraryMonitor source](https://github.com/jellyfin/jellyfin/blob/v10.11.11/Emby.Server.Implementations/IO/LibraryMonitor.cs)
shows the path being handed to the refresher. These sources agree with the
observed HMN family-folder refresh; Created versus Modified was not tested or
changed.

GET `/Environment/DirectoryContents` with both `includeFiles=true` and
`includeDirectories=true` confirms Jellyfin's own filesystem view sees
`/media/adult/HMN/HMN-904` and its exact MP4, NFO, and poster entries. The HMN
family directory returns three entries and the title directory returns three.
The API's `FileSystemEntryInfo` returns only Name/Path/Type, not file sizes;
container-side sizes therefore remain unverified. NAS exact MP4 size matches
the Discovery holding. `JELLYFIN_FS_HMN904_VISIBLE=YES` for existence/type.

A bounded GET inventory with `Recursive=true`,
`IncludeItemTypes=Folder,Movie,Video`, `Fields=Path,ParentId`,
`StartIndex=0`, `Limit=10000` returned 473/473 items:

- `/media/adult`: one Folder, ID `d59216ecad5753389303717a879b33ad`, parent `f27caa37e5142225cceded48f6553502`.
- `/media/adult/HMN`: one Folder, ID `7aed4f1993e9a282c851f3f6da9cf930`, parent `/media/adult`.
- `/media/adult/HMN/HMN-904`: no API folder item.
- `/media/adult/HMN/HMN-904/HMN-904.mp4`: no Movie item.

Comparison title NOSKN-104 is visible in the filesystem endpoint under
`/media/adult/NOSKN/NOSKN-104` (including its MP4 and NFO). Its API hierarchy
also has no title-directory item, but has one Movie at
`/media/adult/NOSKN/NOSKN-104/NOSKN-104.mp4`, ID
`99fbfbd848703e747abdb2d8daac1c11`, parent folder
`/media/adult/NOSKN` (ID `cca74790b4eefebea88f53bfc1342327`). Thus the physical
and API ancestor shape is comparable; HMN's family folder exists and the
refresh targeted it, but no HMN Movie BaseItem appeared.

`JELLYFIN_DB_HIERARCHY=UNKNOWN`: the known host DB path
`/opt/jellyfin/config/data/jellyfin.db` is not present in this execution
host, and the existing `pve` name does not resolve. No alternate access path
was created or attempted. No Jellyfin DB was opened or changed.

Source audit confirms `run_media_pipeline()` builds metadata, publishes the
sidecars, resolves the Adult library, calls `notify_created()`, and immediately
returns `MEDIA_PIPELINE_COMPLETE`; it does not wait for exact item visibility.
Therefore `MEDIA_COMPLETED_MEANS_NOTIFICATION_ACCEPTED_ONLY=YES`.
Classification is `JELLYFIN_PENDING_CLASS=REFRESH_COMPLETED_WITHOUT_ITEM_DISCOVERY`:
the endpoint saw the files, LibraryMonitor logged the HMN parent refresh, no
error was present in the bounded log, yet the exact Movie remained absent
through F4's 120-second GET poll and F5's current GET inventory. No explicit
scan-completion marker exists, so the result identifies the failed discovery
outcome, not a lower-level parser cause.

Current media jobs are COMPLETED=41, FAILED=36, PENDING=11, RUNNING=0. Failed
error classes are CONNECTION_RESET=30 and COVER_URL_MISSING=6. There has been
one proxy-era completed media job: HMN-904. HMN-904 remains COMPLETED/2 and
MFCS-085 remains exhausted/17161.

Production mutation audit: media DB 0, Discovery 0, NAS 0, Jellyfin POST/
refresh/scan/delete 0, Jellyfin DB write 0, completion run 0, timer start 0,
container restart 0, source change 0. Only this canonical handoff is updated.
Keep the timer inactive. Next checkpoint: select one safe Jellyfin indexing
recovery based on the observed HMN parent refresh, then verify by GET; do not
repeat the Created notification or start bulk media recovery in this forensic
checkpoint.

## Post-Stage13 Media-F6 — exact HMN parent refresh did not discover Movie

At source HEAD `c7936dce5ac2a28742a0fbf5ecb93ffb734fc359`, preconditions were
rechecked: completion timer, completion service, and reconcile-apply were
inactive; writer was active with host and web health `READY`; web `/login`
returned 200; delete gate was false. HMN-904 media job 1386103 remained
`COMPLETED / attempt=2`; MFCS-085 remained `FAILED / attempt=17161`. Media
counts remained COMPLETED=41, FAILED=36, PENDING=11, RUNNING=0.

GET `/Items?Ids=7aed4f1993e9a282c851f3f6da9cf930&Fields=Path,ParentId` returned
exactly one item: ID `7aed4f1993e9a282c851f3f6da9cf930`, type `Folder`, path
`/media/adult/HMN`, parent `d59216ecad5753389303717a879b33ad`. The exact HMN-904
Movie path count was 0 before refresh. Jellyfin's filesystem directory listing
for `/media/adult/HMN/HMN-904` showed `HMN-904.mp4`, `HMN-904.nfo`, and
`poster.webp`. Discovery holding 185 remained present=1 at
`HMN/HMN-904/HMN-904.mp4`, size 3,315,951,470 bytes, mtime
1790723785795253379. NAS retained the same MP4 (3,315,951,470 bytes), NFO
(793 bytes), and poster (10,128 bytes).

Exactly one targeted request was sent:
`POST /Items/7aed4f1993e9a282c851f3f6da9cf930/Refresh` with
`metadataRefreshMode=None`, `imageRefreshMode=None`,
`replaceAllMetadata=false`, `replaceAllImages=false`, and
`regenerateTrickplay=false`. It returned HTTP 204 at
2026-09-30 02:50:53 UTC (11:50:53 KST). No library refresh, Created resend,
second refresh, scan, or restart was sent. Exact Movie path polling ran every
two seconds for the 180-second bound (91 GET polls) and remained count 0.

The bounded Jellyfin log window was 02:45:53–02:55:53 UTC (11:45:53–11:55:53
KST). It contained no target refresh execution line, child-discovery evidence,
or refresh error. The only entries were four failed GET probes made during
this checkpoint's preflight (three direct item-route ID format attempts and
one file path passed to the directory-listing endpoint). Thus
`TARGETED_REFRESH_ACCEPTED=YES`,
`TARGETED_REFRESH_EXECUTED=UNKNOWN`, and
`TARGETED_REFRESH_ERROR=NO` for the checked window. Final exact Movie count is
0; parent Folder remains the same single item. Classification:
`TARGETED_PARENT_REFRESH_NO_ITEM_DISCOVERY`,
`TARGETED_PARENT_REFRESH_RECOVERY=FAIL`,
`HMN904_JELLYFIN_VISIBLE=NO`.

After-state checks matched the pre-state: HMN-904 media remained
`COMPLETED / attempt=2`; MFCS-085 remained exhausted; media counts, Discovery
holding identity, and exact NAS sidecars were unchanged. Jellyfin's indexing
was the only production change attempted (one exact parent-refresh POST); no
media DB, Discovery, NAS, completion, timer, or other Jellyfin mutation was
made. The timer remains enabled but inactive, completion service and
reconcile-apply remain inactive, writer remains READY, gate remains false, and
Stage13 remains CLOSED/PASS. Next checkpoint: read-only forensic comparison of
HMN versus a successful family for Jellyfin child resolution/parser inputs;
do not send another refresh or Created notification until separately
authorized.

## Post-Stage13 Media-F7 — HMN-904 vs NOSKN-104 resolver-input forensic

Read-only checks ran at source HEAD `ef687e2a8ff4382e9e76caa66797b150fbe1ce5d`.
The completion timer remained enabled but inactive; completion and
reconcile-apply remained inactive; writer was active and host/web READY; web
`/login` returned 200; gate remained false. No source or production data was
changed. Stage13 remains CLOSED/PASS.

### Exact filesystem and metadata

Jellyfin's exact directory-listing API returned the required children for
both `/media/adult/HMN/HMN-904` and `/media/adult/NOSKN/NOSKN-104`; each has
one regular MP4, one NFO, and one poster. The exact full listing differs:
NOSKN also has `NOSKN-104.ko.srt`; HMN's poster is `poster.webp`, NOSKN's is
`poster.jpg`. `FS_SHAPE_MATCH=YES` for the resolver-relevant movie/NFO/poster
roles, with those full-list differences recorded.

The Jellyfin filesystem endpoint exposes names/types but not mode, uid/gid,
size, or mtime. Exact NAS source stats (on the previously confirmed
read-only Jellyfin media mount) show both title directories and all listed
files are mode 0777, uid 1026, gid 100. HMN sizes are MP4 3,315,951,470 bytes,
NFO 793 bytes, poster 10,128 bytes; NOSKN sizes are MP4 3,669,076,339 bytes,
NFO 810 bytes, poster 26,700 bytes, subtitle 13,519 bytes. Their mtimes differ
by file as expected for separate titles. No filesystem permission difference
was found. Jellyfin-container lstat/stat was unavailable through the existing
read-only interface, so NAS source stat is recorded separately from the
Jellyfin API visibility evidence.

### Jellyfin hierarchy and library settings

GET inventory showed Adult library root `/media/adult`, `CollectionType=movies`,
enabled, and `EnableRealtimeMonitor=true`. Its only `PathInfos` entry is
`/media/adult`; there is no HMN- or NOSKN-specific path override. The library
has `LocalMetadataReaderOrder=[Nfo]` and internet metadata providers disabled.

Both family items are `Folder` children of the same Adult root item
`d59216ecad5753389303717a879b33ad`:

- HMN: ID `7aed4f1993e9a282c851f3f6da9cf930`, path `/media/adult/HMN`.
- NOSKN: ID `cca74790b4eefebea88f53bfc1342327`, path `/media/adult/NOSKN`.

For both titles the title-directory path has no API Folder item. NOSKN has one
Movie at `/media/adult/NOSKN/NOSKN-104/NOSKN-104.mp4`, ID
`99fbfbd848703e747abdb2d8daac1c11`, `MediaType=Video`, `IsFolder=false`,
ParentId `cca74790b4eefebea88f53bfc1342327`. HMN has no Movie at its exact
MP4 path. Therefore the library and parent-folder classifications match;
the inventory difference is the missing HMN Movie child.

### NFO structure

Both exact NFOs parse as XML with root `movie`, one title, one `<id>` equal to
the DVD-ID, and one `<uniqueid type="dvd_id" default="true">` with the same
DVD-ID. Both have one premiered/year, one studio, and one actor; HMN has 7
genres and NOSKN 8. No duplicate or conflicting IDs were found. Both are
`NFO_XML_VALID=YES` and `NFO_STRUCTURE_CLASS=STANDARD_MOVIE_XML`; these
structural differences do not explain why only HMN lacks a Movie item.

### Resolver and ignore-rule comparison

The deployed Jellyfin version is 10.11.11. Its tagged `VideoResolver`
recognizes `.mp4` and runs clean-name/year parsing; `MovieResolver` resolves
movie-library children and its `ResolveMultiple` path filters filenames
matching the whole word `sample`, then passes supported videos to
`VideoListResolver`. The two names `HMN-904.mp4` and `NOSKN-104.mp4` both have
the same plain DVD-ID naming shape, no year token, no `sample` token, and no
CD/DVD/Part/Disc stack suffix. They do not match the resolver's trailer,
sample, or other-extra naming patterns. Static source-based result:
`HMN_VIDEO_RESOLVER_ACCEPTED=YES`,
`NOSKN_VIDEO_RESOLVER_ACCEPTED=YES`; this means the filename/extension rules
do not reject either candidate, not that the full production resolver was
executed in a separate probe.

No `.ignore` exists in the Adult root, either exact family directory, or
either exact title directory; neither exact title listing has a hidden entry
or nested extras directory. The 10.11.11 global ignore patterns include
hidden paths and sample names, but neither exact candidate matches them.
`HMN_IGNORE_RULE_MATCH=NO`; `NOSKN_IGNORE_RULE_MATCH=NO`.

The NOSKN Movie `DateCreated` is 2026-09-08; current Jellyfin log retention
contains only 2026-09-28 through 2026-09-30, so a bounded first-registration
log comparison is `UNKNOWN`. F5 already recorded an HMN family refresh target;
F6's exact parent refresh returned 204 but did not produce the Movie within
180 seconds, with no refresh error in its bounded log window.

Classification: `JELLYFIN_CHILD_RESOLUTION_STATE_ANOMALY`. The resolver-relevant
inputs are equivalent and appear valid, yet only HMN remains unindexed. The
extra NOSKN subtitle and poster extension/content, and expected per-file size
and mtime differences, do not establish a generic rejection rule. No
HMN-specific workaround is recommended. Current media counts are
COMPLETED=41, FAILED=36, PENDING=11, RUNNING=0; failed classes are
CONNECTION_RESET=30 and COVER_URL_MISSING=6. Timer remains inactive. Production
mutation is 0. Next step: investigate the generic child-enumeration/resolver
execution path using server logs or a safe reproduction, without another
refresh, notification, retry, or library scan.

Version-matched source references: [VideoResolver](https://raw.githubusercontent.com/jellyfin/jellyfin/v10.11.11/Emby.Naming/Video/VideoResolver.cs),
[MovieResolver](https://raw.githubusercontent.com/jellyfin/jellyfin/v10.11.11/Emby.Server.Implementations/Library/Resolvers/Movies/MovieResolver.cs),
[NamingOptions](https://raw.githubusercontent.com/jellyfin/jellyfin/v10.11.11/Emby.Naming/Common/NamingOptions.cs),
[IgnorePatterns](https://raw.githubusercontent.com/jellyfin/jellyfin/v10.11.11/Emby.Server.Implementations/Library/IgnorePatterns.cs),
and [Jellyfin `.ignore` documentation](https://jellyfin.org/docs/general/server/media/excluding-directory/).

## Post-Stage13 Media-F8 — deterministic item ID now resolves to visible HMN Movie

Read-only preconditions at starting HEAD
`6dfaa08ba0be548d6199c2e88367233f2dc5d935` were verified: the worktree was
clean and origin matched; completion timer/service and reconcile-apply were
inactive; writer was active and web health `READY`; `/login` returned 200;
gate was false; HMN-904 media job remained `COMPLETED / attempt=2`. During this
checkpoint's API checks, however, the expected exact Movie count was no longer
zero. The current exact path returned one Movie, so the stipulated count=0
precondition had drifted by the time candidate verification ran.

GET `/System/Configuration` returned
`EnableCaseSensitiveItemIds=true`; `/System/Info` confirmed Jellyfin
10.11.11. The version-matched `LibraryManager.GetNewItemId()` implementation
normalizes a key beneath ProgramData only, lowercases the key only when IDs
are case-insensitive, prepends `type.FullName`, then returns the MD5 digest
as a Guid. `GetMD5()` hashes UTF-16LE bytes and constructs a Guid from the
digest bytes. The tested media paths are outside ProgramData, so no path
normalization applies. Source references: [LibraryManager](https://raw.githubusercontent.com/jellyfin/jellyfin/v10.11.11/Emby.Server.Implementations/Library/LibraryManager.cs)
and [BaseExtensions.GetMD5](https://raw.githubusercontent.com/jellyfin/jellyfin/v10.11.11/MediaBrowser.Common/Extensions/BaseExtensions.cs).

The source-derived algorithm was validated against both known-good IDs:

- NOSKN-104 Movie calculated ID equals actual:
  `99fbfbd848703e747abdb2d8daac1c11` (`YES`).
- NOSKN family `Folder` calculated ID equals actual:
  `cca74790b4eefebea88f53bfc1342327` (`YES`).

Calculated HMN candidates:

- `Movie` `/media/adult/HMN/HMN-904/HMN-904.mp4`:
  `ad4c0d7134580158d7b656f7f53f8223`.
- Generic `Video` at the same path:
  `791780d2df49c2f597139bc68ba459f5`.
- `Folder` `/media/adult/HMN/HMN-904`:
  `338a3896277b25272292e68a54838aef`.

Exact-ID GET results: expected Movie candidate present=YES; generic Video
candidate present=NO; title Folder candidate present=NO. The Movie candidate
is one exact `Movie` at the expected path, parented to HMN family Folder
`7aed4f1993e9a282c851f3f6da9cf930`; `MediaType=Video`, `IsFolder=false`, and
`ProviderIds` has key `dvd_id` with value `HMN-904`. `IsVirtualItem` and
`IsMissing` were not exposed in the response.

Adult-root recursive inventory returned 274 items. The HMN identity search
found one item total: Name exactly `HMN-904` matched 0, exact path matched 1,
and `ProviderIds` value `HMN-904` matched 1. No alternate path/type duplicate
was found. The current exact HMN Movie count is 1 and the item appears in
ordinary Adult inventory, so this is not an item-hidden-from-inventory case.

Direct family child comparison: HMN has three children, all `Movie`, including
the one HMN-904 Movie; NOSKN has one child, a `Movie`, its NOSKN-104 control.
Current API child queries are returning the expected items. The deterministic
ID evidence rules out a stale generic Video ID, stale title Folder ID, and
identity collision. The listed F8 classifications A–F do not apply: the
expected Movie exists at the exact path and is visible. Record
`F8_RESULT=INCOMPLETE_PRECONDITION_DRIFT` and
`CURRENT_ITEM_STATE=EXPECTED_MOVIE_PRESENT_AND_VISIBLE`; do not infer which
earlier event caused it to appear.

Production mutation audit: Jellyfin POST/refresh/scan=0; Jellyfin DB write=0;
media DB=0; Discovery=0; NAS=0; completion run=0; timer start=0; source
change=0; restart=0. Timer remains enabled but inactive, service inactive,
writer READY, gate false, and Stage13 CLOSED/PASS. Next checkpoint should
establish the read-only appearance timeline or update the recovery state from
the newly visible item; no additional Jellyfin mutation is indicated by this
forensic result.

## Post-Stage13 Media-F9 — HMN-904 appearance timeline forensic

Read-only preconditions were rechecked at starting HEAD
`e683f4d895a4c3d8bab75bc5d634c7d4d481b5ad`; origin matched and the worktree
was clean. Completion timer was enabled but inactive, completion service and
reconcile-apply were inactive, writer was active, web `/login` returned 200,
delete gate was false, and host writer health was `READY`. HMN-904 remains
`COMPLETED / attempt=2`; Stage13 remains CLOSED/PASS.

### Appearance bounds

F7's last exact Movie-absent inventory is recorded immediately before its
handoff commit at `2026-09-30 12:06:40 KST`; the exact GET wall time was not
retained. F8's first confirmed exact Movie-present GET occurred before its
handoff commit at `2026-09-30 12:17:33 KST`; its exact GET wall time was also
not retained. Therefore the checkpoint-bounded appearance interval is
approximately `2026-09-30 12:06:40–12:17:33 KST`, not an exact event timestamp:
`LAST_KNOWN_ABSENT_KST≈12:06:40`,
`FIRST_KNOWN_PRESENT_KST≤12:17:33`.

GET-only exact-ID lookup returned one `Movie` with ID
`ad4c0d7134580158d7b656f7f53f8223`, exact path
`/media/adult/HMN/HMN-904/HMN-904.mp4`, and parent
`7aed4f1993e9a282c851f3f6da9cf930`. Safe date/identity fields were
`DateCreated=2026-09-29T23:16:25Z` (`2026-09-30 08:16:25 KST`),
`PremiereDate=2026-09-25`, `ProductionYear=2026`, and `ProviderIds.dvd_id=HMN-904`.
`DateLastSaved` was not exposed. `UseFileCreationTimeForDateAdded` was not
exposed by GET `/System/Configuration`; the two known host-side config
candidates were absent, so the effective value is UNKNOWN. Since the reported
DateCreated predates the last-absent checkpoint and the setting is unknown,
DateCreated is not treated as proof of item creation time.

### Event correlation

The bounded Jellyfin log interval was `2026-09-30 03:04:40–03:19:33 UTC`
(`12:04:40–12:19:33 KST`), with the requested two-minute margins around the
checkpoint-bounded appearance interval. The retained log covered through
`03:27:46 UTC`. No matching HMN/HMN-904 refresh, scan, resolver, or error lines
were found: `HMN_REFRESH_EVENT_IN_WINDOW=NO`,
`LIBRARY_SCAN_EVENT_IN_WINDOW=NO`, `RESOLVER_ERROR_IN_WINDOW=NO`.
GET `/ScheduledTasks` showed no execution overlapping the interval; the
`RefreshLibrary` task was Idle with its last completion on September 29, and
the September 30 trickplay task last completed at `03:00 UTC`, before the
interval. Thus no scheduled full-library scan correlates with the appearance.

GET `/Library/VirtualFolders` confirmed Adult root `/media/adult`,
`CollectionType=movies`, and `EnableRealtimeMonitor=true`. Jellyfin 10.11.11
source shows the monitor watches created/changed/renamed/deleted events and
reports changed paths to the refresher; `FileRefresher` uses the configured
`LibraryMonitorDelay` (previously confirmed as 60 seconds). This makes a
realtime watcher a possible natural trigger, but no watcher event or HMN
refresh was evidenced in this appearance window. Version-matched sources:
[LibraryMonitor.cs](https://github.com/jellyfin/jellyfin/blob/v10.11.11/Emby.Server.Implementations/IO/LibraryMonitor.cs)
and [FileRefresher.cs](https://github.com/jellyfin/jellyfin/blob/v10.11.11/Emby.Server.Implementations/IO/FileRefresher.cs).

Two exact-ID GET samples at `12:29:13` and `12:29:23 KST` both returned one
exact Movie: `HMN904_VISIBILITY_STABLE=YES`. Current media counts are
COMPLETED=41, FAILED=36, PENDING=11, RUNNING=0; failure classes remain
CONNECTION_RESET=30 and COVER_URL_MISSING=6. HMN-904 is visible=1. The event
classification is `EVENTUAL_DISCOVERY_TRIGGER_UNATTRIBUTED`: item appearance
is established, but no triggering refresh/scan event was attributable from
available bounded evidence. The Adult realtime watcher remains a source-based
possibility only.

The pipeline contract remains
`MEDIA_COMPLETED_MEANS_NOTIFICATION_ACCEPTED_ONLY=YES`; eventual appearance
does not establish that the prior 120-second wait was sufficient. A future
pipeline design may track Jellyfin visibility in a separate asynchronous
pending/reconciliation state. No source change or production data mutation was
made in F9: Jellyfin writes=0, media DB=0, Discovery=0, NAS=0, completion run=0,
timer start=0, source change=0, restart=0. Timer remains enabled but inactive;
completion service remains inactive; Stage13 remains CLOSED/PASS. Next:
design eventual Jellyfin visibility reconciliation without changing this
read-only forensic result or retrying HMN-904.

## Post-Stage13 Media-F10 — asynchronous Jellyfin visibility reconciliation

Implemented offline source support at starting HEAD
`2cf1768bd0d03e985a76405d2aa9ecd643341f5f`. The media job status contract is
unchanged: `COMPLETED` still means metadata/NFO/poster publication succeeded
and Jellyfin accepted the Created notification with 2xx. It does not mean the
Movie is yet visible. HMN-904 is only a generic fixture label; there is no
HMN-specific production branch.

### Separate visibility state

New module `teddy_discovery_jellyfin_visibility.py` lazily creates
`media_jellyfin_visibility` in the existing media DB during apply-time
reconciliation. Columns are `dvd_id` (unique), `media_job_id`,
`jellyfin_path`, `status`, `check_count`, `media_completed_at`, `created_at`,
`updated_at`, nullable `last_checked_at`, nullable `visible_at`, and nullable
`last_error`. Status is constrained to `PENDING`, `VISIBLE`, or `ATTENTION`.
The table is not created by dry-run/check-only code; no production migration
was applied in F10.

Each reconciliation idempotently seeds visibility only for `media_jobs`
already `COMPLETED` and exactly one current `storage_root='jav', present=1`
Discovery holding. It records the canonical `jellyfin_media_path(relative_path)`;
invalid paths become `ATTENTION`, and missing/ambiguous current holdings are
skipped for a later seed attempt. Failed, pending, and running media jobs do
not seed visibility. Crash recovery is by reseeding a completed job whose
visibility row is still absent.

### GET-only check and runner behavior

`JellyfinClient.exact_media_visibility()` validates canonical Adult path depth,
resolves the exact Adult library root, reads bounded direct root children to
find the family Folder, then reads only that family's direct children and
exact-matches the path. Each child query uses `StartIndex=0`, `Limit=1000`, and
fails closed if its returned count is malformed or incomplete. One exact
Movie is `VISIBLE`; no exact Movie is `PENDING`; duplicate path, wrong type,
ambiguous family/movie parent, malformed response, or invalid path is
`ATTENTION`. GET timeout/connection/HTTP/API failures stay `PENDING`, increment
`check_count`, and store only a bounded error class. `VISIBLE` is terminal.
This flow has no notify, refresh, scan, or other Jellyfin mutation fallback.

The normal apply runner calls visibility reconciliation after its media stage
with independent source default `--jellyfin-visibility-max-items=5`. The
existing `--media-only --media-target-dvd-id` mode passes the same exact target
to visibility reconciliation, so unrelated titles are neither seeded nor
checked in that mode. Runner JSON nests separate `jellyfin_visibility`
`seeded/checked/visible/pending/attention` counters under media; visibility
state never changes the media job's `COMPLETED` status or retry counters.

### Offline verification and production boundary

`teddy_discovery_jellyfin_visibility_smoke.py` covers completed-only seeding,
absent-to-visible eventual discovery, duplicate/wrong-type/parent ambiguity,
malformed and overflow responses, invalid paths, GET timeout handling,
terminal idempotence, media row preservation, exact target isolation, missing
holding, crash-safe seeding, and GET-only request methods. PASS:

- Python compile for the changed modules and smoke fixtures.
- `teddy_discovery_media_jobs_smoke.py`
- `teddy_discovery_media_pipeline_smoke.py`
- `teddy_discovery_media_metadata_smoke.py`
- `teddy_discovery_completion_runner_smoke.py`
- `teddy_discovery_completion_media_smoke.py`
- `teddy_discovery_completion_orchestrator_smoke.py`
- `teddy_discovery_jellyfin_smoke.py`
- `teddy_discovery_jellyfin_visibility_smoke.py`
- `teddy_title_exclusion_smoke.py`
- `teddy_library_delete_jellyfin_smoke.py`

An additional `teddy_library_delete_commit_smoke.py` attempt could not start
because the host Python has no Flask module; no dependency was installed.
F10 made no production deployment, media DB/schema write, media retry,
Jellyfin POST/refresh/scan, wrapper change, or service/timer start. Timer stays
enabled but inactive; completion service remains inactive; Stage13 remains
CLOSED/PASS.

F11 plan: deploy an immutable runtime only after review; keep the timer stopped;
allow the normal apply path to create the visibility table and reconcile the
existing completed cohort using bounded GET-only checks; verify HMN-904 and
known-good completed titles; record any persistent `ATTENTION` states without
Jellyfin mutation; then separately decide remaining media recovery and timer
resumption.

## Post-Stage13 Media-F11 — visibility-state rollout (INCOMPLETE)

Preconditions passed at starting HEAD
`45a99c4cf9d20409ff7ce2cbad83dc8934eb4a66`: local/remote matched and worktree
was clean; completion timer was enabled but inactive; completion and
reconcile-apply services were inactive; writer host/web health was `READY`;
web `/login` returned 200 and delete gate was false. Existing production
runtime was `496043fcd03655b893584f9803f5aaba926a3ff3` at
`/opt/missav-dlp-web/stage9-runtime/releases/496043fcd03655b893584f9803f5aaba926a3ff3`.
Production paths retained from the wrapper are Discovery DB
`/opt/missav-dlp-web/discovery/teddy-discovery.sqlite3`, media DB
`/opt/missav-dlp-web/discovery/teddy-stage9-media.sqlite3`, media writer lock
`/run/lock/teddy-stage9-media-writer.lock`, Jellyfin
`http://192.168.1.205:8096`, and API key path
`/opt/missav-dlp-web/teddy-jellyfin/jellyfin_api_key` (secret not displayed).

### Backup, runtime, and wrapper

Before the visibility DB write, a SQLite backup-API snapshot was created at
`/opt/missav-dlp-web/backups/stage9-f11-20260930-visibility/teddy-stage9-media.before-visibility.sqlite3`.
It opens read-only, `integrity_check=ok`, has the same 88 media rows, counts,
and baseline digest as the source.

Installed immutable runtime
`/opt/missav-dlp-web/stage9-runtime/releases/45a99c4cf9d20409ff7ce2cbad83dc8934eb4a66`
from exact source commit `45a99c4cf9d20409ff7ce2cbad83dc8934eb4a66`. It has 25
Python modules, root ownership, read-only release permissions, exact
`SOURCE_COMMIT` and `.teddy-stage9-commit` markers, and every module SHA-256
matches the repository blob. Compile/import passed.

The previous wrapper was backed up to
`/opt/missav-dlp-web/backups/stage9-f11-20260930-visibility/teddy-completion-stage9-runner.before`
and atomically replaced. It now pins the 45a99c4 runtime and explicitly passes
`--media-poster-proxy-url http://127.0.0.1:58888` and
`--jellyfin-visibility-max-items 5`, retaining the previous production paths,
locks, SSH/Jellyfin options, confirmation, and title-lock root. Inspection
found the old proxy option had been on a shell line after the `exec`; the new
wrapper attaches it to the runner invocation. `bash -n` and runner `--help`
passed. No global proxy environment variables were added. No completion
service was run.

### Baseline and one-off reconciliation

Before reconciliation, `media_jellyfin_visibility` did not exist.
`MEDIA_JOBS_BASELINE_SHA256=c15b4e145bc8007f63398e90153e49885f62ea0d2c12fc28e746c94ce03b6e6c`;
counts were COMPLETED=41, FAILED=36, PENDING=11, RUNNING=0. HMN-904 was
COMPLETED/2 and MFCS-085 was FAILED/17161. `COMPLETED_TOTAL=41`,
`COMPLETED_SEEDABLE=41`, and `COMPLETED_NO_PRESENT_OR_AMBIGUOUS=0`; all 41 had
exactly one present JAV holding, so the preflight target was under the 50-item
bound.

Using only the pinned release, the one-off called
`reconcile_jellyfin_visibility(..., max_items=50, target_dvd_id=None)` directly.
It did not run the normal completion runner, media processor, organizer, or
metadata recovery. A GET-only request guard allowed 82 reconciliation GETs
and would have rejected any non-GET. Result: seeded=41, checked=41,
`VISIBLE=0`, `PENDING=0`, `ATTENTION=41`,
`skipped_no_present_holding=0`; table row count is 41. Every row has
`check_count=1` and reason class `AMBIGUOUS_FAMILY_PARENT`. The attention DVD-ID
list is: ADN-785, ADN-799, AVSA-455, AVSA-456, BAGR-093, DOKI-037, DOKS-689,
DROP-141, DVAJ-754, DVAJ-757, EKDV-826, EROFV-366, EROFV-387, EROFV-390,
FC2-PPV-4973050, GANA-3432, HMN-904, HNBR-014, IESP-765, JUR-750, KIR-079,
MAAN-1193, MILK-306, MIUM-1327, MREC-010, MSFH-048, NAMH-074, NHDTC-247,
NHDTC-250, NLD-033, NOSKN-104, NXGS-025, PRED-054, PRED-451, SDAM-181,
SGKI-106, SIRO-5722, SIRO-5731, START-636, STSK-242, STSK-243.

The guarded reconciler stopped at the family-parent check, before querying any
title's direct children; therefore its zero `VISIBLE` count is not evidence
that those Movie items are absent. A bounded GET-only diagnosis showed the
Adult virtual-folder `ItemId` is a `CollectionFolder` at
`/config/root/default/Adult` (`0a7fd8175719d8f7ebfb93874e55a2d5`), while the
filesystem root `/media/adult` is a separate `Folder`
(`d59216ecad5753389303717a879b33ad`). Adult-root child queries return the
family folders, but their `ParentId` points to the separate `/media/adult`
Folder, not the virtual `CollectionFolder` ID. The current source's strict
comparison treats this Jellyfin hierarchy alias as ambiguous. This is a
resolver assumption to fix and retest before any ATTENTION row is reset or
rechecked; no production visibility status was changed after this diagnosis.

### Protected state and verdict

`MEDIA_JOBS_AFTER_SHA256` equals the baseline exactly; counts remain 41/36/11/0;
HMN-904 remains COMPLETED/2 and MFCS-085 FAILED/17161. Discovery holdings
digest remains
`1d84e3e176a5de3094039a8b049b4924ee475f369c44c4c6fbeff05197c427b7`. NAS was
not accessed for writing. Jellyfin mutations=0. Timer, completion service,
and reconcile-apply remain inactive; writer remains active/READY; web login
remains 200; gate remains false. The expected schema and 41 visibility rows
were the only media-DB changes. No source file, retry, or timer state changed
during F11.

Because `ATTENTION=41`, F11 is `INCOMPLETE`; do not proceed to F12 or resume the
timer. Next checkpoint should correct the Adult `CollectionFolder` versus
filesystem `Folder` parent resolution, prove the corrected direct-child chain
offline, then separately review how to conditionally return these
`AMBIGUOUS_FAMILY_PARENT` rows to `PENDING` before a new bounded GET-only pass.

## Post-Stage13 Media-F11b — virtual/filesystem root alias fix (PASS, source only)

Starting HEAD was `cc61ab0fafa0db9f2a1993b714e67b1729f506a0`; local and
remote matched on `teddy-subtitle-stage11`, with a clean worktree. F11's
41 ATTENTION rows are retained without reset or production GET recheck.
Stage13 remains CLOSED/PASS. Completion timer and service were checked
read-only and remain inactive.

### Corrected hierarchy contract

F11 showed that Adult's virtual CollectionFolder
`0a7fd8175719d8f7ebfb93874e55a2d5` (`/config/root/default/Adult`) exposes
family children whose real parent is filesystem Folder
`d59216ecad5753389303717a879b33ad` (`/media/adult`). Comparing the family
ParentId directly with the virtual ItemId incorrectly rejected that normal
hierarchy.

`teddy_discovery_jellyfin.py` now follows the family's actual ParentId with
`item_by_id()`: a bounded GET `/Items?Ids=...&Fields=Path,ParentId` with
StartIndex=0, Limit=1, images/user data disabled. The input must be a canonical
lowercase compact or hyphenated GUID. The response must contain exactly one
item with the requested ID and valid nonempty Type/Path fields. The parent
must be Type=Folder and Path exactly `/media/adult`. Only then are the
family's direct children checked for an exact Movie with ParentId=family.Id.
Virtual and filesystem IDs may differ; no server-specific ID is embedded
in production logic.

Missing family or Movie remains PENDING. Duplicate family/Movie, wrong type,
missing parent, malformed exact-parent response, wrong root path/type, and
wrong Movie parent remain ATTENTION (including the existing malformed-response
mapping). Transport/API errors retain the existing PENDING behavior. No
POST, refresh, scan, retry, or repair fallback was introduced.

### Offline validation

PASS: Jellyfin, Jellyfin visibility, completion runner, completion-media,
media jobs, media pipeline, and title-exclusion smokes (7/7), plus Python
compile and `git diff --check`. Tests used injected HTTP responses and
temporary SQLite databases; no production Jellyfin requests were made.

The alias fixture uses virtual-adult and a separate canonical GUID for
filesystem-adult, with a Folder at `/media/adult`. It proves VISIBLE both at
the client and through the actual reconciler writing a temporary DB. Negative
fixtures cover wrong root type/path, empty or missing family ParentId,
malformed parent response/identity/count/fields, missing family/Movie,
duplicate Movie/family, and wrong Movie parent. The opener rejects every
non-GET request. Invalid exact IDs fail before network access. Existing
Created-notification smoke behavior is unchanged. The existing visibility
smoke's duplicate/wrong-type loop indentation was corrected so both cases
exercise their temporary DB state transition.

### F11c repair plan — not executed

1. Keep timer and completion service inactive. Verify the new source commit,
   deploy using the existing immutable runtime convention, and verify the
   corrected runtime before any reset. Do not run normal completion apply.
2. Take a fresh read-only production snapshot and consistent SQLite backup.
   Match the exact 41 DVD-IDs recorded in F11, media_job_id, jellyfin_path,
   media_completed_at and F11 check timestamps to the F11 cohort. Verify
   completed media identities/present holdings and unchanged media_jobs
   digest. Any unexplained cohort drift stops repair.
3. Under the existing media writer lock and a single transaction, recheck each
   captured row's full identity and allow only rows with status=ATTENTION,
   check_count=1, and last_error exactly
   `ATTENTION:AMBIGUOUS_FAMILY_PARENT`. Update only status to PENDING;
   preserve check_count, timestamps and error until the reconciler records
   its next observation. Require exactly the approved 41 rows affected;
   rollback the entire transaction on any mismatch. No other ATTENTION
   reason is eligible. Do not use an unrestricted status-only reset.
4. Run only bounded GET-only visibility reconciliation (max_items=50) from
   the corrected release. Confirm HMN-904 and NOSKN-104 VISIBLE, inspect
   remaining PENDING/ATTENTION, and compare media_jobs/Discovery digests.
   Leave timer inactive and report before deciding F12.

This checkpoint executed no production SQL, visibility reset, Jellyfin GET
recheck/POST, refresh/scan, media retry, runtime deployment, wrapper update,
or service/timer start. Production visibility rows remain untouched; the
last verified production state is the F11 cohort of 41 ATTENTION rows.
F11b has no blocker; F11c conditional repair design is ready for its own
checkpoint. Source changes here are not yet installed in production.

## Post-Stage13 Media-F11c — conditional visibility repair (PASS)

Starting HEAD was `494134bf50d58db7d2eb148ec1a870f6526b5d11`, equal to remote
on `teddy-subtitle-stage11`, with a clean worktree. Completion timer/service
and reconcile-apply were inactive, writer host/web health READY, `/login`
200, delete gate false. Stage13 remains CLOSED/PASS.

### Backup and corrected production runtime

SQLite backup API snapshot:
`/opt/missav-dlp-web/backups/stage9-f11c-20260930-visibility/teddy-stage9-media.before-conditional-reset.sqlite3`.
It opens read-only, passes integrity_check, matches the media_jobs digest,
and contains exactly the preflight 41 ATTENTION rows. The F11 backup was not
overwritten. The same backup directory retains the preflight snapshot,
old wrapper, reset result, reconciler result, and post-verification record.

Installed immutable release:
`/opt/missav-dlp-web/stage9-runtime/releases/494134bf50d58db7d2eb148ec1a870f6526b5d11`.
All 25 module hashes match that exact Git commit; SOURCE_COMMIT and the
existing runtime marker match; compile and all module imports pass. Release
ownership is root:root with read-only files/directory, and old releases remain.
The normal wrapper was backed up and atomically repinned from 45a99c4 to
494134bf. All other arguments remain byte-for-byte unchanged, including
poster proxy `http://127.0.0.1:58888`, visibility max-items=5, DB paths and
locks. `bash -n` passes; no global proxy environment was added and the
completion service was not run.

### Exact cohort and transaction

Before mutation: media jobs COMPLETED=41, FAILED=36, PENDING=11, RUNNING=0;
visibility rows=41, all ATTENTION. All 41 match the DVD-ID list recorded in
F11, status=ATTENTION, check_count=1,
last_error=`ATTENTION:AMBIGUOUS_FAMILY_PARENT`, visible_at=NULL, and non-null
jellyfin_path. Every row matches its completed media_job_id/completion time
and one exact present JAV holding. created_at, updated_at and last_checked_at
all span the same single timestamp `2026-09-30T04:08:36+00:00`
(`2026-09-30 13:08:36 KST`), identifying the F11 pass.

Using only the corrected pinned runtime's media writer lock/transaction
helper, the full 41-row snapshot and media_jobs digest were rechecked inside
the transaction. The UPDATE additionally restricted DVD-ID to that exact
cohort, status=ATTENTION, check_count=1, the exact error above, visible_at=NULL
and non-null jellyfin_path. Only status=PENDING and updated_at=current UTC
were changed; other fields were verified unchanged before commit.
`RESET_CANDIDATES=41`, `RESET_ROWCOUNT=41`. Any snapshot or rowcount mismatch
would have rolled back the transaction. Reset/recheck occurred at
`2026-09-30 13:37:50 KST`.

### One corrected GET-only pass

Called only `reconcile_jellyfin_visibility(..., max_items=50,
target_dvd_id=None)` once. The injected request guard rejects non-GETs and
unexpected endpoints; it observed 164 GETs and zero non-GETs. The production
chain is now virtual Adult root -> exact family -> exact actual parent
Folder at `/media/adult` -> family direct Movie children.

Result: seeded=0, checked=41, VISIBLE=41, PENDING=0, ATTENTION=0,
skipped_no_present_holding=0. All original rows retain identity/creation
fields, have check_count=2, visible_at set, and last_error=NULL.
HMN-904 is VISIBLE at `/media/adult/HMN/HMN-904/HMN-904.mp4`;
NOSKN-104 is VISIBLE at `/media/adult/NOSKN/NOSKN-104/NOSKN-104.mp4`.
Both visible_at values are `2026-09-30T04:37:50+00:00`.
Residual PENDING title list: empty. No further check/reset/refresh was run.

### Protected-state verification and next step

The media_jobs digest uses compact JSON arrays of media_job_id, dvd_id,
status, attempt_count, error, created_at, updated_at ordered by media_job_id.
Baseline and after SHA-256 both equal the F11 digest:
`c15b4e145bc8007f63398e90153e49885f62ea0d2c12fc28e746c94ce03b6e6c`.
Counts remain 41/36/11/0. HMN-904 remains COMPLETED/2; MFCS-085 remains
FAILED/17161.

Discovery holdings compact-array digest, ordered by holding_id, is unchanged:
`79daee7af1192905ad1a2730a704a8c23a17559efd96b227d73d3eb266606fe8`.
The Discovery database file SHA-256 is also unchanged:
`883145a2db1d9f17624b32742217d4509a2aa965555fa82277d45752c4a226d3`.
NAS writes=0; Jellyfin mutations=0; media_jobs writes=0. The authorized
visibility reset/check state updates, runtime install and wrapper replacement
are the only production changes made by this checkpoint (plus backup files).
No normal completion run, media retry, organizer, metadata recovery,
container restart, timer start, or gate change occurred.

Final runtime: completion timer enabled/inactive, completion service inactive,
reconcile-apply inactive, writer active with host/web READY, web running with
restart count 0, `/login` 200, gate=false. F11c PASS, no blocker.
Next F12: review remaining CONNECTION_RESET recovery separately from
COVER_URL_MISSING, plan bounded media recovery, and decide timer resumption
only after that checkpoint's safety/results checks. Timer remains inactive.


## Post-Stage13 Media-F12 — current-input retry guard (PASS, source only)

Starting HEAD `c0f7939fb73583e201a3bf7baf5e550f10ec589c` matched remote and
the worktree was clean. The current production runtime remains the F11c
`494134bf50d58db7d2eb148ec1a870f6526b5d11` release. F11c visibility
remains VISIBLE=41, PENDING=0, ATTENTION=0; Stage13 remains CLOSED/PASS.
The production completion timer stays enabled/inactive; the service and
reconcile-apply stay inactive. The audit opened media and Discovery SQLite
read-only with query_only and did no filesystem/NAS scan or network fetch.

### Current remaining cohort

At audit `2026-09-30T04:47:49.366643+00:00`, FAILED=36 and PENDING=11; RUNNING=0.
FAILED old CONNECTION_RESET=30: current cover READY=30, MISSING=0.
FAILED old COVER_URL_MISSING=6: still MISSING=6, now READY=0.
PENDING=11: current cover READY=10, MISSING=1, INVALID=0.
All 47 have exactly one present JAV holding. Existing retry policy
(max attempts=5, FAILED backoff=3600 seconds, stale RUNNING=7200 seconds)
returns ELIGIBLE=46 and EXHAUSTED=1 at the audit time. FAILED attempts:
35 at 1, one at 17161; PENDING attempts: all 11 at 0. The exhausted
MFCS-085 also has a missing cover URL, so raw missing-input count=7, while
the mutually exclusive recovery cohort HELD_INPUT_MISSING has 6.

| DVD-ID | Job | Attempts | Old error class | Updated UTC | Current input | Present JAV | Old eligibility | New cohort |
| --- | --- | ---: | --- | --- | --- | ---: | --- | --- |
| MFCS-085 | FAILED | 17161 | COVER_URL_MISSING | 2026-09-29T03:31:57+00:00 | HELD_COVER_URL_MISSING | 1 | EXHAUSTED | EXHAUSTED |
| FNS-244 | FAILED | 1 | CONNECTION_RESET | 2026-09-29T23:20:55+00:00 | READY | 1 | ELIGIBLE | READY_TRANSIENT_RECOVERY |
| MAAN-945 | FAILED | 1 | COVER_URL_MISSING | 2026-09-29T23:22:25+00:00 | HELD_COVER_URL_MISSING | 1 | ELIGIBLE | HELD_INPUT_MISSING |
| MIAD-866 | FAILED | 1 | CONNECTION_RESET | 2026-09-29T23:30:45+00:00 | READY | 1 | ELIGIBLE | READY_TRANSIENT_RECOVERY |
| EBWH-296 | FAILED | 1 | CONNECTION_RESET | 2026-09-29T23:32:22+00:00 | READY | 1 | ELIGIBLE | READY_TRANSIENT_RECOVERY |
| MIRD-258 | FAILED | 1 | CONNECTION_RESET | 2026-09-29T23:33:57+00:00 | READY | 1 | ELIGIBLE | READY_TRANSIENT_RECOVERY |
| SKMJ-774 | FAILED | 1 | CONNECTION_RESET | 2026-09-29T23:35:17+00:00 | READY | 1 | ELIGIBLE | READY_TRANSIENT_RECOVERY |
| EROFV-313 | FAILED | 1 | CONNECTION_RESET | 2026-09-29T23:36:40+00:00 | READY | 1 | ELIGIBLE | READY_TRANSIENT_RECOVERY |
| SVVRT-086 | FAILED | 1 | CONNECTION_RESET | 2026-09-29T23:37:54+00:00 | READY | 1 | ELIGIBLE | READY_TRANSIENT_RECOVERY |
| NTR-102 | FAILED | 1 | COVER_URL_MISSING | 2026-09-29T23:39:11+00:00 | HELD_COVER_URL_MISSING | 1 | ELIGIBLE | HELD_INPUT_MISSING |
| DAL-012 | FAILED | 1 | CONNECTION_RESET | 2026-09-29T23:40:24+00:00 | READY | 1 | ELIGIBLE | READY_TRANSIENT_RECOVERY |
| FTHT-361 | FAILED | 1 | CONNECTION_RESET | 2026-09-29T23:41:40+00:00 | READY | 1 | ELIGIBLE | READY_TRANSIENT_RECOVERY |
| FTHTD-219 | FAILED | 1 | CONNECTION_RESET | 2026-09-29T23:43:03+00:00 | READY | 1 | ELIGIBLE | READY_TRANSIENT_RECOVERY |
| FTHTD-228 | FAILED | 1 | CONNECTION_RESET | 2026-09-29T23:44:19+00:00 | READY | 1 | ELIGIBLE | READY_TRANSIENT_RECOVERY |
| MARR-014 | FAILED | 1 | CONNECTION_RESET | 2026-09-29T23:47:07+00:00 | READY | 1 | ELIGIBLE | READY_TRANSIENT_RECOVERY |
| FTKD-045 | FAILED | 1 | CONNECTION_RESET | 2026-09-29T23:48:27+00:00 | READY | 1 | ELIGIBLE | READY_TRANSIENT_RECOVERY |
| KNMB-133 | FAILED | 1 | CONNECTION_RESET | 2026-09-29T23:49:39+00:00 | READY | 1 | ELIGIBLE | READY_TRANSIENT_RECOVERY |
| VDD-209 | FAILED | 1 | CONNECTION_RESET | 2026-09-29T23:50:47+00:00 | READY | 1 | ELIGIBLE | READY_TRANSIENT_RECOVERY |
| DLDSS-557 | FAILED | 1 | CONNECTION_RESET | 2026-09-29T23:52:09+00:00 | READY | 1 | ELIGIBLE | READY_TRANSIENT_RECOVERY |
| YSN-665 | FAILED | 1 | CONNECTION_RESET | 2026-09-29T23:53:26+00:00 | READY | 1 | ELIGIBLE | READY_TRANSIENT_RECOVERY |
| NPJS-264 | FAILED | 1 | CONNECTION_RESET | 2026-09-29T23:54:49+00:00 | READY | 1 | ELIGIBLE | READY_TRANSIENT_RECOVERY |
| FC2-PPV-4983582 | FAILED | 1 | COVER_URL_MISSING | 2026-09-29T23:56:11+00:00 | HELD_COVER_URL_MISSING | 1 | ELIGIBLE | HELD_INPUT_MISSING |
| SKMJ-426 | FAILED | 1 | CONNECTION_RESET | 2026-09-29T23:57:38+00:00 | READY | 1 | ELIGIBLE | READY_TRANSIENT_RECOVERY |
| DVMM-015 | FAILED | 1 | CONNECTION_RESET | 2026-09-29T23:59:04+00:00 | READY | 1 | ELIGIBLE | READY_TRANSIENT_RECOVERY |
| DLDSS-555 | FAILED | 1 | CONNECTION_RESET | 2026-09-30T00:00:31+00:00 | READY | 1 | ELIGIBLE | READY_TRANSIENT_RECOVERY |
| DLDSS-559 | FAILED | 1 | CONNECTION_RESET | 2026-09-30T00:02:02+00:00 | READY | 1 | ELIGIBLE | READY_TRANSIENT_RECOVERY |
| ROYD-353 | FAILED | 1 | CONNECTION_RESET | 2026-09-30T00:03:15+00:00 | READY | 1 | ELIGIBLE | READY_TRANSIENT_RECOVERY |
| HUNTC-623 | FAILED | 1 | CONNECTION_RESET | 2026-09-30T00:04:41+00:00 | READY | 1 | ELIGIBLE | READY_TRANSIENT_RECOVERY |
| HODV-22113 | FAILED | 1 | CONNECTION_RESET | 2026-09-30T00:05:43+00:00 | READY | 1 | ELIGIBLE | READY_TRANSIENT_RECOVERY |
| HODV-22114 | FAILED | 1 | CONNECTION_RESET | 2026-09-30T00:06:48+00:00 | READY | 1 | ELIGIBLE | READY_TRANSIENT_RECOVERY |
| HODV-22116 | FAILED | 1 | CONNECTION_RESET | 2026-09-30T00:07:50+00:00 | READY | 1 | ELIGIBLE | READY_TRANSIENT_RECOVERY |
| HODV-22112 | FAILED | 1 | CONNECTION_RESET | 2026-09-30T00:08:56+00:00 | READY | 1 | ELIGIBLE | READY_TRANSIENT_RECOVERY |
| PRIAN-060 | FAILED | 1 | COVER_URL_MISSING | 2026-09-30T00:10:00+00:00 | HELD_COVER_URL_MISSING | 1 | ELIGIBLE | HELD_INPUT_MISSING |
| WA-576 | FAILED | 1 | CONNECTION_RESET | 2026-09-30T00:11:05+00:00 | READY | 1 | ELIGIBLE | READY_TRANSIENT_RECOVERY |
| SKMJ-790 | FAILED | 1 | CONNECTION_RESET | 2026-09-30T00:12:10+00:00 | READY | 1 | ELIGIBLE | READY_TRANSIENT_RECOVERY |
| PRIAN-059 | FAILED | 1 | COVER_URL_MISSING | 2026-09-30T00:13:15+00:00 | HELD_COVER_URL_MISSING | 1 | ELIGIBLE | HELD_INPUT_MISSING |
| FC2-PPV-4982148 | PENDING | 0 | NONE | 2026-09-29T23:50:46+00:00 | HELD_COVER_URL_MISSING | 1 | ELIGIBLE | HELD_INPUT_MISSING |
| DSOD-046 | PENDING | 0 | NONE | 2026-09-29T23:52:09+00:00 | READY | 1 | ELIGIBLE | READY_PENDING_FIRST_ATTEMPT |
| CAWB-039 | PENDING | 0 | NONE | 2026-09-29T23:53:25+00:00 | READY | 1 | ELIGIBLE | READY_PENDING_FIRST_ATTEMPT |
| MFYD-181 | PENDING | 0 | NONE | 2026-09-29T23:54:49+00:00 | READY | 1 | ELIGIBLE | READY_PENDING_FIRST_ATTEMPT |
| NIMA-086 | PENDING | 0 | NONE | 2026-09-29T23:56:11+00:00 | READY | 1 | ELIGIBLE | READY_PENDING_FIRST_ATTEMPT |
| MIDA-705 | PENDING | 0 | NONE | 2026-09-29T23:57:37+00:00 | READY | 1 | ELIGIBLE | READY_PENDING_FIRST_ATTEMPT |
| MIDA-746 | PENDING | 0 | NONE | 2026-09-29T23:59:04+00:00 | READY | 1 | ELIGIBLE | READY_PENDING_FIRST_ATTEMPT |
| MIDV-822 | PENDING | 0 | NONE | 2026-09-30T00:00:31+00:00 | READY | 1 | ELIGIBLE | READY_PENDING_FIRST_ATTEMPT |
| MIDA-445 | PENDING | 0 | NONE | 2026-09-30T00:02:01+00:00 | READY | 1 | ELIGIBLE | READY_PENDING_FIRST_ATTEMPT |
| MIDV-372 | PENDING | 0 | NONE | 2026-09-30T00:03:14+00:00 | READY | 1 | ELIGIBLE | READY_PENDING_FIRST_ATTEMPT |
| MIDV-925 | PENDING | 0 | NONE | 2026-09-30T00:04:40+00:00 | READY | 1 | ELIGIBLE | READY_PENDING_FIRST_ATTEMPT |

Recovery cohorts, mutually exclusive:

- `EXHAUSTED` (1): MFCS-085.
- `HELD_INPUT_MISSING` (6): FC2-PPV-4982148, FC2-PPV-4983582, MAAN-945, NTR-102, PRIAN-059, PRIAN-060.
- `READY_PENDING_FIRST_ATTEMPT` (10): CAWB-039, DSOD-046, MFYD-181, MIDA-445, MIDA-705, MIDA-746, MIDV-372, MIDV-822, MIDV-925, NIMA-086.
- `READY_TRANSIENT_RECOVERY` (30): DAL-012, DLDSS-555, DLDSS-557, DLDSS-559, DVMM-015, EBWH-296, EROFV-313, FNS-244, FTHT-361, FTHTD-219, FTHTD-228, FTKD-045, HODV-22112, HODV-22113, HODV-22114, HODV-22116, HUNTC-623, KNMB-133, MARR-014, MIAD-866, MIRD-258, NPJS-264, ROYD-353, SKMJ-426, SKMJ-774, SKMJ-790, SVVRT-086, VDD-209, WA-576, YSN-665.

### Source behavior and offline proof

`teddy_discovery_media_metadata.media_input_eligibility()` reads only the
current `titles.cover_url` for a canonical DVD-ID. It returns READY or
HELD_METADATA_NOT_FOUND / HELD_COVER_URL_MISSING / HELD_COVER_URL_INVALID.
READY requires a nonempty ASCII http(s) URL with host, usable port and
percent escapes, no credentials or whitespace. It does no network probe
and never uses the historical media-job error as the decision source.
Thus an old COVER_URL_MISSING row becomes READY when current input is valid;
an old CONNECTION_RESET row holds if current input disappears.

The normal completion runner passes its Discovery DB path into
`run_retryable_media_jobs()`. The runner retains the existing eligibility,
backoff, max-attempt and title-lock policies; after an eligible job has the
title lock, it rechecks current input before marking RUNNING. A HOLD leaves
status, attempt_count, error and updated_at unchanged and calls no processor.
Exact `--media-only --media-target-dvd-id` uses the same guard, with no
unrelated fallback. The direct media-runner argument is optional for
legacy/offline callers; the normal production runner always supplies it.
New result counters identify each input HOLD reason.

Offline fixtures prove missing/invalid/not-found input, old-error
self-healing, transient retry, first attempt, exact-target isolation, no
attempt/processor on HOLD, ordering under the title lock, and backoff before
the guard. PASS: media metadata, media jobs, media pipeline, completion
runner, completion-media, Jellyfin, Jellyfin visibility and title-lock
smokes (8/8); Python compile and diff check PASS. These tests used only
temporary databases and injected responses.

F12 production mutation=0: no runtime deployment, wrapper change, media
retry, poster fetch, Jellyfin POST/refresh/scan, Discovery/NAS write,
completion/timer start or visibility update. Stage13 remains CLOSED/PASS.
Next F12b: keep timer stopped; select exactly one READY_TRANSIENT_RECOVERY
job (the earliest is FNS-244), revalidate proxy/input/backoff and run one
controlled exact-target media-only retry. If that succeeds, separately
consider one READY_PENDING_FIRST_ATTEMPT job (earliest DSOD-046). Keep the
COVER_URL_MISSING and EXHAUSTED cohorts held under their existing policies.
Timer resumption requires a later checkpoint.

## Post-Stage13 Media-F12b — FNS-244 transient recovery canary (PASS)

Starting HEAD `7e2b32ea8b70d6b678a95dacd03ec44ba093afba` matched remote on
`teddy-subtitle-stage11` with a clean worktree. Completion timer enabled but
inactive, completion and reconcile-apply services inactive, writer host/web
READY, web `/login` 200, gate=false. Stage13 remains CLOSED/PASS.

### Runtime and exact preflight

FNS-244 was FAILED, attempt_count=1, current input guard READY, existing
retry_eligibility ELIGIBLE. It had one present JAV holding (holding_id=167,
`FNS/FNS-244/FNS-244.mp4`, size 3646558138). The exact NAS directory
contained only `FNS-244.mp4` and `FNS-244.ko.srt`; NFO/poster were absent.
Existing Jellyfin visibility cohort was 41 VISIBLE, 0 PENDING, 0 ATTENTION,
with no FNS-244 visibility row.

Immutable release installed at
`/opt/missav-dlp-web/stage9-runtime/releases/7e2b32ea8b70d6b678a95dacd03ec44ba093afba`.
All 25 runtime modules match the exact repository blobs and compile/import;
`SOURCE_COMMIT` and runtime marker match. Root ownership/read-only release
policy retained, old releases retained. Production wrapper backed up to
`/opt/missav-dlp-web/backups/stage9-f12b-20260930-wrapper.before` and
atomically repinned to this release. All other wrapper options stayed
byte-for-byte unchanged, including poster proxy
`http://127.0.0.1:58888`, visibility max-items=5, DB/SSH/Jellyfin paths,
locks and confirmation. `bash -n` passed. No normal service/timer run.

The exact stored cover URL was read from Discovery without printing it;
scheme=https, hostname=`www.javdatabase.com`. Running Gluetun maps
`127.0.0.1:58888 -> 8888/tcp`. A poster-only proxy opener returned HTTP 200,
`image/webp`, and a successful 64-byte bounded read. No direct fallback or
full poster download was used for this probe.

### One exact media-only run

Immediate precheck still found FAILED/1, READY input and ELIGIBLE backoff.
Invoked the pinned runner once with the production paths and options plus
`--media-only --media-target-dvd-id FNS-244 --media-max-items 1`.
Result: `attempted=1`, `completed=1`, `failed=0`, target=FNS-244,
organizer=SKIPPED_MEDIA_ONLY, metadata recovery=SKIPPED_MEDIA_ONLY.
Media pipeline returned MEDIA_PIPELINE_COMPLETE and one normal
`JELLYFIN_NOTIFIED` Created response; no manual notification, refresh,
scan or retry occurred. FNS media job is now COMPLETED/2 with error NULL.

The exact NAS title directory now has the original MP4 (same 3646558138
bytes), one `FNS-244.nfo` (621 bytes), one `poster.webp` (10290 bytes), and
the preexisting subtitle. Temp/partial count=0. No unrelated title path was
used by the media-only pipeline.

The run seeded and checked only FNS-244 visibility: VISIBLE=1, PENDING=0,
ATTENTION=0, check_count=1. A later separate GET-only exact visibility check
also returned VISIBLE, Jellyfin Movie ID
`0791d23c738f72763c6390aeb3db49fa`. The existing 41 visibility rows
are byte-for-byte identical to the protected snapshot, so the table now
contains 42 VISIBLE rows. This respects the async visibility contract even
though this canary happened to become visible immediately.

### Protected-state comparison

Unrelated media_jobs digest before and after:
`667573c1608a95dc1cddb583a61d276fb11f4a89710d11e3c2eed3d18c397abc`.
Existing visibility-41 digest:
`dc8228a87b5906e321f547d66f2b857b804996992200362bfbfea13d87044762`
(before/after full rows identical). Discovery holdings digest:
`87ac2a009759f7ffd03ae95b03cc3caef455f1a58ce44e110f25999de577bdea`
(before/after); Discovery DB file SHA-256 also unchanged from baseline.
MFCS-085 remains FAILED/17161. The six other HELD_INPUT_MISSING rows and
all 11 PENDING rows retain their exact status, attempt, error and updated_at.
New media counts are COMPLETED=42, FAILED=35, PENDING=11, RUNNING=0.

Authorized production mutations were limited to immutable runtime install,
wrapper repin, FNS-244 media row transition, FNS-244 sidecar publish, its one
normal Jellyfin Created notification and FNS-244 visibility seed/check.
Discovery write=0; unrelated media/visibility/NAS mutation=0. Completion
timer remains enabled/inactive, completion service and reconcile-apply
inactive, writer host/web READY, web running with restart count 0, `/login`
200, delete gate=false. F12b PASS, no blocker.

Next F12c: review this successful transient canary and decide whether one
READY_PENDING_FIRST_ATTEMPT title should be run as a separate exact
media-only canary. Timer resumption remains a separate decision after that.

## Post-Stage13 Media-F12c — DSOD-046 first-attempt canary (PASS)

Starting HEAD `7f4d5cdeb42af7ba2a91527a0890d1ff055154b3` matched origin on
`teddy-subtitle-stage11` with a clean worktree. The production wrapper was
pinned to immutable runtime `7e2b32ea8b70d6b678a95dacd03ec44ba093afba`.
Completion timer was enabled but inactive; completion and reconcile-apply
services inactive; writer host/web READY; web `/login` 200; gate=false.
Stage13 remains CLOSED/PASS.

### Preflight and proxy

DSOD-046 was PENDING/attempt=0/error NULL, current-input guard READY and
existing retry eligibility ELIGIBLE, with exactly one present JAV holding:
holding_id=209, `DSOD/DSOD-046/DSOD-046.mp4`, 4105052908 bytes.
It had no visibility row. Before run, the existing 42 visibility rows were
all VISIBLE. Protected media rows, visibility rows and Discovery holdings
were saved as exact snapshots and digests.

The stored cover URL was read without printing it. The explicit poster-only
opener used `http://127.0.0.1:58888`; Gluetun mapping remained
`127.0.0.1:58888 -> 8888/tcp`. Probe returned HTTP 200,
`image/webp`, and a 64-byte bounded read. No direct fallback/full poster
probe was used.

### One exact first attempt

Immediately before execution, DSOD-046 still passed status, input and
backoff preflight. Ran the pinned production runner directly once with
production paths/options and `--media-only --media-target-dvd-id DSOD-046
--media-max-items 1`, apply and the existing confirmation. Result:
attempted=1, completed=1, failed=0; organizer and metadata recovery were
both `SKIPPED_MEDIA_ONLY`. The title lock/current-input guard was on the
production runner path. Transition: PENDING/0/error NULL to
COMPLETED/1/error NULL. Pipeline returned MEDIA_PIPELINE_COMPLETE and one
normal Created notification result `JELLYFIN_NOTIFIED`.

The exact NAS title directory contains the original MP4, one
`DSOD-046.nfo` (888 bytes) and one `poster.webp` (13782 bytes), with no
partial/temp files. MP4 size remains 4105052908 and remote mtime_ns exactly
matches the Discovery holding baseline `1790725928629214263`.

The run seeded and checked only DSOD-046 visibility. Result:
VISIBLE=0, PENDING=1, ATTENTION=0, check_count=1,
last_error=`EXACT_MOVIE_NOT_VISIBLE`, exact canonical path
`/media/adult/DSOD/DSOD-046/DSOD-046.mp4`. This is an allowed eventual
visibility state; no further notify, refresh, scan or media retry was sent.

### Protected-state comparison and readiness

DSOD-046-excluded media_jobs digest stayed
`dbffea89e44ab1fb5c7b8414b141b686d53a93416733fb3d9ec562c962391d7a`.
All existing 42 visibility rows exactly match their pre-run snapshot
(digest `3c23d33aacb6272b66d0f5db0653e5906d984bb62ca6c4ea726717a4221d1ec9`);
the only visibility addition is DSOD-046 PENDING/1. Discovery holdings
digest stayed
`87ac2a009759f7ffd03ae95b03cc3caef455f1a58ce44e110f25999de577bdea`, and
its database file SHA-256 stayed unchanged. FNS-244 remains COMPLETED/2,
HMN-904 COMPLETED/2, MFCS-085 FAILED/17161; the six HELD_INPUT_MISSING rows
and all other PENDING rows retain their pre-run state. Unrelated Discovery,
NAS and Jellyfin changes=0. No timer/service start or container restart.

`TIMER_RESUME_READY=YES`: F12b transient retry passed; F12c first attempt
passed; the current-input HOLD contract and poster-only proxy passed offline
and through this canary; visibility reconciler recorded the expected
PENDING state without ATTENTION; protected state stayed unchanged. Timer
remains enabled/inactive, completion service inactive, writer READY,
`/login` 200, gate=false. F12c PASS, no blocker.

Next F12d: perform the separate timer-resume decision and controlled
observation of queued work. The first timer start is not part of F12c.

## Post-Stage13 Media-F12d — normal service canary / timer resume (INCOMPLETE)

Starting HEAD `b3a64b56f689ceb0e793f5dad59054b4e86afac5` matched remote on
`teddy-subtitle-stage11` with a clean worktree. Runtime wrapper pinned to
`7e2b32ea8b70d6b678a95dacd03ec44ba093afba`, poster proxy
`http://127.0.0.1:58888`, visibility bound=5. Before service execution the
timer was enabled/inactive, completion and reconcile-apply inactive, writer
host/web READY, login=200, gate=false.

### Actual timer contract

`/etc/systemd/system/teddy-completion-stage9.timer` is enabled and defines
`OnActiveSec=60s`, `OnUnitInactiveSec=60s`, `AccuracySec=5s`,
`RandomizedDelaySec=0`, `Persistent=false`, Unit=`teddy-completion-stage9.service`.
While inactive its realtime next elapse is empty. At checkpoint start its
last trigger was `2026-09-30 09:13:15 KST`.

The completion service is Type=oneshot, runs the installed normal wrapper,
and has `TimeoutStartSec=3600`. The bounded normal planner read-only
preflight found downloads=0, organizer eligible=0/held=0, metadata recovery
candidates=0 (bound=1). Normal wrapper bounds were organizer=1,
media=1, visibility GET=5; no separate planner item was available to apply.

### Manual normal service run

Started `teddy-completion-stage9.service` exactly once while the timer was
inactive at `14:13:56 KST`. It exited successfully at `14:13:58 KST`
(exit status 0, duration about 2 seconds). Organizer applied=0; media
reconciliation created=0; metadata recovery attempted=0. Media runner
attempted=1/completed=1/failed=0 and completed MIAD-866 from FAILED/1 to
COMPLETED/2. MAAN-945 was held as HELD_COVER_URL_MISSING without consuming
an attempt; exhausted=1 remained MFCS-085. Visibility seeded=1, checked=2,
visible=44, pending=0, attention=0. DSOD-046 moved from visibility
PENDING to VISIBLE in that GET-only reconciliation. MIAD-866 received one
normal Created notification; its exact NAS directory has its MP4, one NFO
and one poster, without temp/partial files.

### Timer start and immediate-trigger guard

After verifying the manual result, started the already-enabled timer at
`14:16:33 KST`. The associated service had entered inactive at
`14:13:58 KST`, so its `OnUnitInactiveSec=60s` deadline was already overdue
by more than a minute. The timer immediately activated the service at
`14:16:33 KST`. The monitor detected the new ExecMainStartTimestamp and
stopped the timer immediately. This is
`TIMER_IMMEDIATE_TRIGGER=YES` / `OVERDUE_TIMER_IMMEDIATE_TRIGGER`.

The timer-triggered normal service completed at `14:16:35 KST` with exit
status 0. Its normal bounds again applied: organizer=0, metadata recovery=0,
media attempted=1/completed=1/failed=0, visibility GET checked=1 and
attention=0. It completed EBWH-296 from FAILED/1 to COMPLETED/2, held
MAAN-945 as HELD_COVER_URL_MISSING without an attempt, and preserved the
MFCS-085 exhausted state. Visibility seeded EBWH-296 and completed with
VISIBLE=45/PENDING=0/ATTENTION=0. This was the one timer-triggered run caught
by the guard; no additional timer run occurred.

### Protected state and final state

Final media counts are COMPLETED=45, FAILED=33, PENDING=10, RUNNING=0.
The only media rows changed from the pre-canary snapshot were MIAD-866 and
EBWH-296, both FAILED/1 to COMPLETED/2 with error NULL. The six
HELD_INPUT_MISSING rows and all ten PENDING rows exactly match their
pre-run snapshots. MFCS-085 remains FAILED/17161. FNS-244 and HMN-904 remain
COMPLETED/2.

All 45 visibility rows are VISIBLE; ATTENTION=0. DSOD-046 is VISIBLE.
Discovery holdings digest and entire Discovery DB file hash match the
pre-run snapshot. Organizer applied=0, so no new Discovery/NAS holding was
created. The only NAS paths written were the two normal bounded media titles
MIAD-866 and EBWH-296, each with one NFO and one poster; their MP4s remain.
No Jellyfin refresh/scan or container restart occurred.

The completion timer remains enabled but inactive; completion service and
reconcile-apply are inactive; no next timer elapse is scheduled while stopped.
Writer remains READY, web login=200, gate=false. Stage13 remains CLOSED/PASS.
The service canary passed, but F12d is INCOMPLETE because the overdue
`OnUnitInactiveSec` event caused an immediate run. Timer resumption readiness
is NO until the timer restart contract is corrected or otherwise safely
proved. Next checkpoint: design and validate a timer re-arm policy that
cannot replay a stale unit-inactive deadline; keep the timer inactive during
that work, then repeat the bounded immediate-trigger check before leaving
normal automation active.

## Post-Stage13 Media-F12e — fresh-inactive timer re-arm (INCOMPLETE)

Starting HEAD `4b2f040bde6dc232de80df0442e2a704cf2a377a` matched the remote
branch and the worktree was clean. The production wrapper remained pinned to
runtime `7e2b32ea8b70d6b678a95dacd03ec44ba093afba`. Before the run, the
completion timer was enabled/inactive, the completion service and
reconcile-apply were inactive, writer host/web health was READY, `/login`
returned 200, and the delete gate was false. The timer contract is unchanged:
`OnActiveSec=60s`, `OnUnitInactiveSec=60s`, `AccuracySec=5s`,
`RandomizedDelaySec=0`, `Persistent=false`.

### Read-only preflight and baseline

The production planner found zero downloads/plans, zero organizer work, and
zero metadata recovery candidates (normal metadata bound=1). Media retry
policy found 32 FAILED jobs ELIGIBLE, one EXHAUSTED, and ten PENDING ELIGIBLE.
The six current-input-missing rows were
`FC2-PPV-4982148`, `FC2-PPV-4983582`, `MAAN-945`, `NTR-102`, `PRIAN-059`,
and `PRIAN-060`; the ten PENDING rows were
`CAWB-039`, `FC2-PPV-4982148`, `MFYD-181`, `MIDA-445`, `MIDA-705`,
`MIDA-746`, `MIDV-372`, `MIDV-822`, `MIDV-925`, and `NIMA-086`.
MFCS-085 was FAILED/17161.

Before the manual service run, media counts were 45/33/10/0
(COMPLETED/FAILED/PENDING/RUNNING), all 45 visibility rows were VISIBLE, and
ATTENTION=0. Baseline digests were media_jobs
`ebbbc109b8ec9ae02bfde2fe394f3847a1558edb6e41ccda41979ff80921fb86`,
visibility `cdcaf72d305859d3445348414b1ca63ed1eb0c14fbe5af411448558ca8ce2882`,
and Discovery holdings `87ac2a009759f7ffd03ae95b03cc3caef455f1a58ce44e110f25999de577bdea`
(218 rows).

### One manual normal service run

With the timer still inactive, started `teddy-completion-stage9.service`
exactly once at `2026-09-30 14:33:08 KST`. It exited at `14:33:09 KST` with
`Result=success` and `ExecMainStatus=0`. The bounded run had no organizer
plans/applies and no metadata recovery attempts. Media reconciled=0 and
attempted=1/completed=1/failed=0; MIRD-258 moved from FAILED/1 to
COMPLETED/2. One missing-cover job was held without consuming an attempt and
the exhausted count remained one. Visibility seeded=1 and checked=1, ending
VISIBLE=46/PENDING=0/ATTENTION=0; MIRD-258 is VISIBLE with check_count=1.

Final media counts are COMPLETED=46, FAILED=32, PENDING=10, RUNNING=0; the
only changed media row is MIRD-258. All six HELD_INPUT_MISSING rows, all ten
PENDING rows, and MFCS-085 FAILED/17161 are unchanged. Discovery holdings
digest is unchanged. The full media_jobs digest is now
`ebf0af2e9c19a242e3559d04247c75399125c2142fd5fafbb7fb450463637fc5`.
The visibility table has 46 VISIBLE rows and no PENDING/ATTENTION rows.

### Fresh timer re-arm was safely skipped

The orchestration helper raised a local `TypeError` while formatting the
integer `media_job_id` in its post-run safety report. This happened after the
manual service completed and before the timer-start section. A read-only
recheck confirmed RUNNING=0, the six held-input rows and MFCS-085 unchanged,
visibility ATTENTION=0, and the Discovery holdings digest unchanged. The
service's fresh inactive timestamp was `2026-09-30 14:33:09 KST`. When the
recheck then measured elapsed time, 45.117 seconds had passed, exceeding the
required 10-second re-arm window. Therefore `systemctl start
teddy-completion-stage9.timer` was not issued; timer start count=0,
`TIMER_IMMEDIATE_TRIGGER=NOT_RUN`, and the first scheduled run was not
observed. The timer remains enabled but inactive with no next elapse; the
completion service and reconcile-apply remain inactive. Writer host/web are
READY, `/login`=200, and gate=false.

`COMPLETION_AUTOMATION_RESUMED=NO`. F12e is INCOMPLETE because the fresh
inactive deadline was not re-armed within 10 seconds and no timer-triggered
run was observed. Stage13 remains CLOSED/PASS. Do not infer an immediate
trigger result from this run. Next checkpoint: perform one fresh normal
service run and, in the same bounded orchestration, capture its inactive
timestamp and start the already-enabled timer within 10 seconds; retain the
10-second immediate-trigger guard and verify the first scheduled run before
leaving automation active.

## Post-Stage13 Media-F12f — atomic fresh timer re-arm (PASS)

Starting HEAD `5daa5bf935451ddd99e2bdb5e074bbdfac1df99d` matched the remote
branch and the worktree was clean. The normal completion wrapper remained
pinned to runtime `7e2b32ea8b70d6b678a95dacd03ec44ba093afba`, with
poster-only proxy `http://127.0.0.1:58888` and visibility bound=5. Before
execution, timer and completion service were inactive, reconcile-apply was
inactive, writer host/web health was READY, `/login`=200, gate=false, and
RUNNING=0. The timer remained enabled and its unit was unchanged
(`OnActiveSec=60s`, `OnUnitInactiveSec=60s`, `AccuracySec=5s`,
`RandomizedDelaySec=0`, `Persistent=false`).

### Baseline and fresh re-arm

Read-only baseline: media COMPLETED/FAILED/PENDING/RUNNING=46/32/10/0;
visibility=46 VISIBLE, 0 PENDING, 0 ATTENTION. The six
HELD_INPUT_MISSING rows were `FC2-PPV-4982148`, `FC2-PPV-4983582`, `MAAN-945`,
`NTR-102`, `PRIAN-059`, and `PRIAN-060`; the ten PENDING IDs were
`CAWB-039`, `FC2-PPV-4982148`, `MFYD-181`, `MIDA-445`, `MIDA-705`,
`MIDA-746`, `MIDV-372`, `MIDV-822`, `MIDV-925`, and `NIMA-086`.
MFCS-085 was FAILED/17161. Baseline digests: media_jobs
`ebf0af2e9c19a242e3559d04247c75399125c2142fd5fafbb7fb450463637fc5`,
visibility `421ce357e3748aa08f7136036790b66dc13bb36be2a595bd2e1c2d72e26e6413`,
Discovery holdings (218 rows)
`87ac2a009759f7ffd03ae95b03cc3caef455f1a58ce44e110f25999de577bdea`.

Started the normal systemd completion service exactly once at
`2026-09-30 14:44:24 KST`; it returned success, `ExecMainStatus=0`, and became
inactive at `14:44:28 KST`. Without a report parser, database query, or JSON
formatting between service completion and timer activation, started the
already-enabled timer at `14:44:28 KST`. The service inactive timestamp was
`Wed 2026-09-30 14:44:28 KST`; measured
`REARM_DELAY_SECONDS=0.022`. Timer entered active/waiting with a future next
elapse. The full 10-second guard passed:
`TIMER_IMMEDIATE_TRIGGER=NO`.

### First scheduled run and protected state

The first scheduled trigger occurred at `14:45:28 KST`; its service
invocation exited successfully at `14:45:29 KST` (`ExecMainStatus=0`). The
manual run had organizer applied=0, metadata recovery attempted=0, media
attempted=1/completed=1/failed=0, held-missing=1, exhausted=1, and visibility
seeded=1/checked=1/ATTENTION=0. It completed SKMJ-774 from FAILED/1 to
COMPLETED/2; the normal media pipeline reported `JELLYFIN_NOTIFIED` and
visibility recorded the exact title VISIBLE.

The scheduled run likewise applied no organizer or metadata recovery work and
attempted one media job, completing EROFV-313 from FAILED/1 to COMPLETED/2.
It held MAAN-945 without an attempt, retained exhausted=1, and seeded/checked
one visibility row. The pipeline reported `JELLYFIN_NOTIFIED`; EROFV-313 is
VISIBLE. No explicit refresh or scan was sent.

Because the timer intentionally remained active, seven further normal
scheduled cycles occurred while the handoff was being finalized:

| Scheduled start (KST) | Media completed | Exit | Visibility |
| --- | --- | --- | --- |
| 14:46:30 | SVVRT-086 | 0 | VISIBLE; ATTENTION=0 |
| 14:47:36 | DAL-012 | 0 | VISIBLE; ATTENTION=0 |
| 14:48:40 | FTHT-361 | 0 | VISIBLE; ATTENTION=0 |
| 14:49:46 | FTHTD-219 | 0 | VISIBLE; ATTENTION=0 |
| 14:50:50 | FTHTD-228 | 0 | VISIBLE; ATTENTION=0 |
| 14:51:56 | MARR-014 | 0 | VISIBLE; ATTENTION=0 |
| 14:53:00 | FTKD-045 | 0 | VISIBLE; ATTENTION=0 |

Each cycle had planner total=0, organizer applied=0, metadata recovery=0,
media attempted=1/completed=1/failed=0, exhausted=1, and one or two
current-input missing-cover HOLDs depending on candidates encountered.
Each normal media pipeline reported `JELLYFIN_NOTIFIED`; the visibility
reconciler seeded/checked one item and found no PENDING or ATTENTION item.

At the latest read-only audit, media counts were COMPLETED=55, FAILED=23,
PENDING=10, RUNNING=0; the changed media rows from baseline were
SKMJ-774, EROFV-313, SVVRT-086, DAL-012, FTHT-361, FTHTD-219, FTHTD-228,
MARR-014, and FTKD-045, each FAILED/1 to COMPLETED/2. All six input-HOLD
rows, all ten PENDING rows, and MFCS-085 FAILED/17161 are unchanged.
Discovery holdings digest is unchanged. Visibility was 55 VISIBLE, 0 PENDING,
0 ATTENTION. Media jobs digest at this audit was
`88473c9fdc3c163b7bb865e0396b5eb49744990a7382637cbcc8776382683742`;
visibility digest was
`2378e58848f4c8d2c94cbd339c67ff50515237e5282ae4af0c31ba4471721319`.
Writer host/web remain READY, `/login`=200, and gate=false.

The completion timer remains enabled and active/waiting; completion service
and reconcile-apply are inactive. At the latest timer query, last trigger was
`2026-09-30 14:53:00 KST` and next elapse was `14:54:01 KST`. No timer stop,
unit edit, daemon-reload, web restart, or writer restart occurred.
`COMPLETION_AUTOMATION_RESUMED=YES`; Stage13 remains CLOSED/PASS. Normal
bounded completion automation is resumed with the existing HOLD, exhausted,
and visibility policies; subsequent timer cycles are normal operation.
