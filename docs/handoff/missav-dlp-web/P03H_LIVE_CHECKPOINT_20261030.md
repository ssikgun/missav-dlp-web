# P03-H Stage9 NFO title-only live checkpoint — 2026-10-30 KST

CANONICAL_BRANCH: `teddy-subtitle-stage11`
WORKSTREAM: `stage9-media`
TASK_ID: `STG9MEDIA-001`
TASK_STATUS: `IN_PROGRESS`
COMMON_CONTRACT: `1.0.1 / APPROVED`
STAGE9_CONTRACT: `1.0.0 / APPROVED`
BASE_REMOTE_SHA_AT_CHECK: `b6da0ff8423bef0b56be6c1772c6f1740f34eb5d`

## Most recent user-confirmed evidence

- Exact frozen 188-candidate manifest SHA-256: `87ff398ba60f7b062fd07152c82aa3696fe7c8746cbbf530d206f8d51540e087`. It was derived from 247 previously inspected title-prefix candidates, excluding 53 bare-prefix cases and 13 owner-mismatch cases (59 unique exclusions).
- `EBWH-350/movie.nfo` prior successful title-prefix single-file canary, with Jellyfin detail and work-number search verified by user.
- `MARR-014/MARR-014.nfo` canary: originally SHA-256 `bdd46f7b26559f9fb8820deecd615d81acf3c4a73c5a06cc22c6b09c15bba360`, updated `8e053717574731599da4a01ca382beb88cd655712ac4ed5fd64f159a230b9b8b`. Exact NAS backup at `/volume1/video/video2/downloads/backups/stage9/p03h-marr014-20261030-174521-0ax70_67/MARR-014.nfo.original` passed user hash verification; updated file owner `ssikgun:users`, mode `777`, size `519`. User confirmed Jellyfin work-number search and detail title `[MARR-014]` PASS after full scan.
- User explicitly approved title-only updates for the **remaining exact 187**, subject to preconditions; this is *not* blanket permission for other content, access policy, or unrelated resources.

## Most recent 187 read-only NAS preflight

- User CT108 result: `TARGET_187=PASS`, `VERIFIED_119=104`, `VERIFIED_129=83`, `BLOCKED=0`, `NAS_WRITE=0 DB_WRITE=0 JELLYFIN_WRITE=0`.
- Preflight script SHA-256 `95dd7700135daeee3c9b4a1da418da1b12484ad6b5adeb8971a4c8bb87fd9dbf`.
- Result manifest SHA-256 `994ffbf9ecf36a6d3a01c3c54c393cd21404a1dd6d3d6a5e45b8bffbfb2ad2b9`; CT108 result path `/tmp/p03h-readonly187-7gdqwhtt/results.jsonl`.
- 104 canonical `<DVD-ID>.nfo` files: owner `ssikgun`, write-access `True`, `SYNO_ACL_V1`; current candidate for cautious bounded `ssikgun` batches.
- 83 `movie.nfo` files: owner `admin`, write-access `False` as `ssikgun`, ACL GET failed (`ACL_GET_FAILED`); **LIVE UPDATE BLOCKED** pending separate safe privilege/metadata-preserving method. Do not infer that read-only check establishes replacement permission.
- `MARR-014` and other 59 excluded files must never be included in subsequent batches. Remaining 187 have not yet been changed.

## 104-file bounded execution preparation

- New one-off `p03h_bulk104_ssikgun_controlled.py` is an *external scratch artifact*, not canonical product code. Reported draft SHA-256 `14a9b65fe87768d8c27598d7a88bb7352aa26fdb6cadcf81f1fcbee570e81cef`. Offline synthetic checks reported PASS; **real NAS dry-run and apply NOT RUN**.
- Before use: verify script bytes/SHA, exact frozen manifest and exclusion filter, per-NFO current hash, source identity, original bytes backup and readback, owner/group/mode/ACL consistency, interruption handling, and bounded stop-on-error. No unsafe inference from a mock.
- Intended first checkpoint: inspect the script, then NAS dry-run for first 10 of 104; only after that evidence should a live small batch run. Never automatically advance after error.
- Keep historical backup artifacts; no destructive cleanup or ad hoc privilege expansion.
- `stage9_media` remains the least-privilege File Station production publisher; manual `ssikgun` maintenance is distinct and must not become the Stage9 service identity.
- No Stage9 timer changes. Proposed P03-T hourly-to-10-minute timer is **last step, NOT RUN**.
- Protect other workstreams `DLDWS-001` and `S11-WX011`; no Downloader, Writer, Stage11 source/DB/service changes.

## Crash-safe continuation rule

At each significant checkpoint (first bounded batch, next batch result, the 104-file cohort complete, separate 83-file decision, and final Jellyfin validation), append a new dated checkpoint in GitHub on the **same canonical branch** before advancing. Verify the remote branch SHA and new file readback. Do not overwrite or truncate the large historical ACTIVE_WORK/CURRENT_HANDOFF documents merely to prepend a small log. Historical `NEXT` text is not a new approval.

STATUS_SUMMARY: `MARR014=PASS; PREFLIGHT_187=PASS; LIVE_104=NOT_RUN; LIVE_83=BLOCKED; BULK_187=IN_PROGRESS; P03_T=NOT_RUN`.


## Verified first-10 NAS dry-run — 2026-10-30 KST, user CT108 evidence

- Stage9 approved bulk candidate, user authorization from the earlier 187-target approval remains limited to 187 exact candidates; protected other 59 files and already finished MARR-014 are excluded.
- On CT108, local script `/tmp/p03h_bulk104_ssikgun_controlled.py` passed SHA-256 `14a9b65fe87768d8c27598d7a88bb7352aa26fdb6cadcf81f1fcbee570e81cef`; 188 JSONL manifest passed SHA-256 `87ff398ba60f7b062fd07152c82aa3696fe7c8746cbbf530d206f8d51540e087`.
- Synology normal SSH user `ssikgun` staging directory `/tmp/p03h-bulk104-sIzAT42z` contains copied verified script and manifest; both hashes validated again on NAS.
- `--offline-plan` and `--dry-run --start 0 --count 10` both PASS, with 104 exact ssikgun targets, MARR-014 excluded, 83 admin-owned targets excluded.
- The exact first 10 identities, in ascending order: `ACHJ-097,ADN-785,ADN-799,AVSA-455,AVSA-456,BAGR-093,CAWB-039,DAL-012,DANDYA-049,DASS-534`.
- User-visible results: `PREFLIGHT=10_PASS; DRY_RUN=PASS; NAS_WRITE=0 DB_WRITE=0 JELLYFIN_WRITE=0`.
- **First live apply NOT RUN at this checkpoint.** Following step within existing user-approved 187 scope: recheck NAS-staged script/manifest hashes, execute only `--apply --start 0 --count 10 --confirm P03H-104` as non-sudo `ssikgun`, preserve verified backup receipts, stop immediately if any error, and record actual applied count/IDs and NAS backup path in the next GitHub checkpoint.
- The batch script uses in-place writes, not atomic rename. The preflight PASS does not prove power-loss atomicity or rule out uncooperative concurrent file writers. Backups are created/read back for all 10 before NFO mutations; errors trigger per-file recovery attempt and stop. Never blindly retry after partial failure.
- The remaining 94 within this 104 cohort have NOT RUN. Admin-owned 83 are still BLOCKED by account write-access and ACL read failures. Stage9 service account, timers, NAS ACL policy, videos, DB, and Jellyfin unchanged.

LATEST_STATUS: `FIRST10_DRYRUN=PASS; FIRST10_APPLY=NOT_RUN; LIVE_104=NOT_RUN; LIVE_83=BLOCKED; P03_T=NOT_RUN`.


## P03-H first 10 live apply — 2026-10-30 23:21 KST (user terminal log)

- User ran NAS normal `ssikgun`, non-sudo `python3 -B p03h_bulk104_ssikgun_controlled.py --apply --start 0 --count 10 --confirm P03H-104`. Exact NAS staged script SHA256 `14a9b65fe87768d8c27598d7a88bb7352aa26fdb6cadcf81f1fcbee570e81cef` and frozen 188 manifest SHA256 `87ff398ba60f7b062fd07152c82aa3696fe7c8746cbbf530d206f8d51540e087` both verified PASS in user log.
- `PREFLIGHT=10_PASS`, `BATCH_BACKUP=PASS`, `BATCH=PASS; APPLIED_COUNT=10`, `NAS_NFO_WRITE=10; VIDEO_WRITE=0 DB_WRITE=0 JELLYFIN_WRITE=0`, `JELLYFIN_REFRESH=NOT_RUN`.
- Backup: `/volume1/video/video2/downloads/backups/stage9/p03h-bulk104-20261030-232101-jfneyo0r` (per-ID original.nfo, original_acl.txt, receipt.json).
- Applied exact IDs: `ACHJ-097, ADN-785, ADN-799, AVSA-455, AVSA-456, BAGR-093, CAWB-039, DAL-012, DANDYA-049, DASS-534`.
- Applied NFO SHA256 in above order: `ab68d15a40a2990be4536d8d77286d011b8c37a7375567f0b8659760755b0809`, `819d29338cda63aba564efee28e7ac277da9e41cd62bc0a7cc324efb5812e413`, `e264cc5a77a55b17720498cc31c8c702419149f12219368a6024bfa358d658dd`, `ba7862170073ee27604d1ea5eb50320c768f393691605ee7e804d3a1b3022161`, `afee042ad3e7281b92ab7afd41b464dd80c682bc74a23d2a1b4dd967a8a5b8fc`, `aba4512e326786a8af047207ea78ece0dbc2b4d9dac996e63fcd16fe5a86a49c`, `61f4ea6238ac73d7328c42c423a62bc59885c3a6335f81c701fb71eb540a94d8`, `e5a13f22da6f5f01fac8ec590d0bc286818c21fcd6d55edfebc9f3bcf5edbbca`, `d8c9caf825bf107c57716fbf824bfc66bc60af5709121182b3e367484cefd53f`, `82481c793a3ecddac49361c6b061d01e081012435ddf6f060ed8a2b8eaee50d4`.
- This is user-supplied execution evidence, not independent second NAS readback. Next: read-only 10-target receipt/backup/NFO hash, ACL and owner/mode check; stop if mismatch. DO NOT rerun first batch.
- Remaining: 94 `ssikgun` writable + 83 `admin` inaccessible. MARR-014 and protected 59 excluded. No timer, Stage9 account or unrelated service change. Stage9 timer 10-min change still NOT RUN.

LATEST_STATUS: `FIRST10_APPLY=PASS_10; FIRST10_INDEPENDENT_POSTCHECK=NOT_RUN; REMAINING_104=94; LIVE_83=BLOCKED; JELLYFIN_REFRESH=NOT_RUN; P03_T=NOT_RUN`.


## First 10 independent NAS postcheck — 2026-10-30 KST (user terminal evidence)

- Following the exact first-10 live application, user executed a **read-only** Python verification under NAS non-sudo `ssikgun` over SSH from CT108. Exact manifest SHA-256 was checked against `87ff398ba60f7b062fd07152c82aa3696fe7c8746cbbf530d206f8d51540e087`.
- Inspected the ten identity-matched `receipt.json`, `original.nfo`, `original_acl.txt`, and current canonical NFOs under the first-batch backup directory `/volume1/video/video2/downloads/backups/stage9/p03h-bulk104-20261030-232101-jfneyo0r`.
- For every one of `ACHJ-097, ADN-785, ADN-799, AVSA-455, AVSA-456, BAGR-093, CAWB-039, DAL-012, DANDYA-049, DASS-534`, the program printed `PASS=<DVD-ID> BACKUP=OK NFO=OK ACL=OK`.
- Checks included exact original backup SHA against immutable manifest and backup receipt; updated NFO bytes exactly equal to insertion of `[DVD-ID] ` into the original title only; expected updated SHA; inode, UID, GID, mode, regular-file/link count; Synology ACL hash and extended attribute names unchanged.
- Terminal summary: `POSTCHECK=10_PASS`; `NAS_WRITE=0 DB_WRITE=0 JELLYFIN_WRITE=0`. This PASS is based on user's NAS terminal output, not a separate GitHub-side NAS connection.
- **First 10 are COMPLETE / verified; NEVER reapply start=0.** This did not include Jellyfin library rescan. Keep original backups intact.
- Next checkpoint is next-batch `--dry-run --start 10 --count 10` from the **same verified NAS staging directory** `/tmp/p03h-bulk104-sIzAT42z`, with exact script+manifest SHA checks. If PASS, authorized separate apply for same bounded ten and independent postcheck; stop immediately on any mismatch. Do not include 83 inaccessible admin-owned files or protected 59, and do not change Stage9 timers yet.

LATEST_STATUS: `FIRST10_APPLY=PASS_10; FIRST10_INDEPENDENT_POSTCHECK=PASS_10; REMAINING_104=94; LIVE_83=BLOCKED; JELLYFIN_REFRESH=NOT_RUN; P03_T=NOT_RUN`.
