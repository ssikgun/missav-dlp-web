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


## Second 10 (offset 10–19) NAS dry-run — 2026-10-30 KST, CT108 user evidence

- Executed on Synology via SSH using regular non-sudo `ssikgun`, staging `/tmp/p03h-bulk104-sIzAT42z`, with immutable source inputs.
- Script SHA-256 `14a9b65fe87768d8c27598d7a88bb7352aa26fdb6cadcf81f1fcbee570e81cef` PASS; 188-row manifest SHA-256 `87ff398ba60f7b062fd07152c82aa3696fe7c8746cbbf530d206f8d51540e087` PASS.
- Exact command `python3 -B p03h_bulk104_ssikgun_controlled.py --dry-run --start 10 --count 10`.
- Exact IDs in sorted batch: `DLDSS-536,DLDSS-555,DLDSS-557,DLDSS-559,DOKI-037,DOKS-689,DROP-141,DSOD-046,DVAJ-754,DVAJ-757`.
- Verified reported: `TARGETS_104=PASS; EXCLUDE_MARR014=YES; EXCLUDE_ADMIN83=YES`, `BATCH_START=10; BATCH_COUNT=10`, `PREFLIGHT=10_PASS`, `DRY_RUN=PASS; NAS_WRITE=0 DB_WRITE=0 JELLYFIN_WRITE=0`.
- **Second batch actual apply NOT RUN at this checkpoint**. User's standing approval covers exactly remaining 187 existing NFO title-only modifications, contingent on original backup and post-apply verification; no admin-owned, protected-59 or MARR-014 modifications. Previous first 10 independently checked PASS, do not reapply them.
- Next checkpoint: verify hashes and exact second-batch IDs on NAS then `--apply --start 10 --count 10 --confirm P03H-104`; stop on any error and avoid blind retry. Record actual backup folder, applied hashes and completion count before further operations. Continue recording to GitHub canonical branch.

LATEST_STATUS: `FIRST10_POSTCHECK=PASS_10; SECOND10_DRYRUN=PASS_10; SECOND10_APPLY=NOT_RUN; TOTAL_APPLIED=10_OF_187; ADMIN83=BLOCKED; STAGE9_TIMER=UNCHANGED`.


## Second 10 live NFO apply — 2026-10-30, user CT108/NAS result

- Live user evidence only (not an independent GitHub-side NAS readback): ran as NAS non-sudo `ssikgun`, exact staging script and immutable 188 manifest both SHA-256 verification PASS.
- Command: `python3 -B p03h_bulk104_ssikgun_controlled.py --apply --start 10 --count 10 --confirm P03H-104`.
- Source manifest SHA-256: `87ff398ba60f7b062fd07152c82aa3696fe7c8746cbbf530d206f8d51540e087`. Script SHA-256: `14a9b65fe87768d8c27598d7a88bb7352aa26fdb6cadcf81f1fcbee570e81cef`.
- `PREFLIGHT=10_PASS`, `BATCH_BACKUP=PASS`, `BATCH=PASS; APPLIED_COUNT=10`, `NAS_NFO_WRITE=10; VIDEO_WRITE=0 DB_WRITE=0 JELLYFIN_WRITE=0`, `JELLYFIN_REFRESH=NOT_RUN`.
- NAS preserved backup root: `/volume1/video/video2/downloads/backups/stage9/p03h-bulk104-20261030-233103-pbrtrzep`.
- Applied IDs and after SHA-256:
  - DLDSS-536: `88b5d07f05616e3ecb2145a976ae5e3ff93d2afa5190c68438a8460fcc408401`
  - DLDSS-555: `a229655d40e9244ad2dad474a41686f5338f19fc3637af5a3659969fa36169c6`
  - DLDSS-557: `d6db1c957f35063b465bc9a8271dd2375aa23997daa6ab71574eef81fe98a1a9`
  - DLDSS-559: `7e1fe4f495758c1186462baeb3efef4c5ad90d8c6401fab8e4736a6a5d3310a7`
  - DOKI-037: `6ae8e46681aa8d41517436e401e5cdf688d1bd6079db5d88b0c972f0037a7872`
  - DOKS-689: `b0c6ed6c8452c1f977870aba5b5937f54d02d68d57b3e62a5c0020e5bef91c56`
  - DROP-141: `d30a35724e0cfbf57ddf257074c5327a6c9507604dd88342991074cde4bf88c0`
  - DSOD-046: `bdc065a4c24013e37dac70f370f5cd51f73b9d55a29fb98bd851936e307b05f0`
  - DVAJ-754: `51ecb09899b576fa82e4837f6fbe098e675a2b2f9ebaa046cf3d2f053e5441b4`
  - DVAJ-757: `9110c6c036892979643351afe86ac602d8c9b6e1f4ed181b14d65868f8b259de`
- **Next step:** independently verify exactly these ten immutable original backups, receipts, on-disk current NFOs, SHA-256 and Synology ACL/owner/group/mode. No reapply or arbitrary retry.
- User asks to increase subsequent batch size. Current inspected batch script `MAX_BATCH=20`; recommend batches of **up to 20** from exact remaining 104 target set only after successful second-batch independent postcheck. No program change authorized/needed for 20. Next prospective batch offset `--start 20 --count 20`, subject to dry-run PASS. Other 83 admin-owned remain BLOCKED.
- Earlier 10 independently confirmed PASS; now **20 total applied**, of exact 187 approved: 84 more `ssikgun` + 83 `admin`. Jellyfin refresh for recent changes NOT_RUN.
- No Stage9 service credentials, ACL policy, existing video, product DB, Jellyfin, protected 59, completed MARR-014 or timer changes.

LATEST_STATUS: `FIRST10_POSTCHECK=PASS_10; SECOND10_APPLY=PASS_10; SECOND10_INDEPENDENT_POSTCHECK=NOT_RUN; APPLIED_TOTAL=20_OF_187; REMAINING_104=84; LIVE_83=BLOCKED; P03_T=NOT_RUN`.


## Second 10 independent NAS postcheck — 2026-10-30 KST, user terminal

- Exact follow-up to second batch live application (`--start 10 --count 10`), backup directory `/volume1/video/video2/downloads/backups/stage9/p03h-bulk104-20261030-233103-pbrtrzep`.
- User ran CT108 SSH to NAS as normal `ssikgun` with read-only Python: checked frozen 188-manifest SHA `87ff398ba60f7b062fd07152c82aa3696fe7c8746cbbf530d206f8d51540e087`, selected sorted manifest offset 10–19 against exact expected DVD IDs, checked `receipt.json` and `original.nfo` bytes/SHA against manifest, saved ACL SHA, current NFO expected title-only prefix bytes and candidate SHA, inode/UID/GID/mode/link count, live Synology ACL hash and xattrs.
- All ten printed `BACKUP=OK NFO=OK ACL=OK`: `DLDSS-536,DLDSS-555,DLDSS-557,DLDSS-559,DOKI-037,DOKS-689,DROP-141,DSOD-046,DVAJ-754,DVAJ-757`.
- Summary: `POSTCHECK=10_PASS`; `NAS_WRITE=0 DB_WRITE=0 JELLYFIN_WRITE=0`. All checks based on user-supplied CT108/NAS terminal evidence, not separately connected NAS by GitHub.
- **First 20/187 are now applied and independently verified. Do not reapply offsets 0–19.** Remaining `ssikgun` subset 84, `admin`-owned inaccessible subset 83. Preserve all original backups.
- User requested larger batches and approved rollout; existing reviewed batch program limit `MAX_BATCH=20`. **Next single checkpoint**: verify NAS script + manifest SHA and execute dry-run only `--dry-run --start 20 --count 20` (indices 20–39 in 104 ssikgun-owned cohort) under original NAS staging `/tmp/p03h-bulk104-sIzAT42z`; actual apply must wait until dry-run result is observed. No change to code, admin permissions, unrelated workstream, Stage9 timer or Jellyfin DB.

LATEST_STATUS: `FIRST10_POSTCHECK=PASS_10; SECOND10_APPLY=PASS_10; SECOND10_INDEPENDENT_POSTCHECK=PASS_10; APPLIED_TOTAL=20_OF_187; REMAINING_104=84; LIVE_83=BLOCKED; NEXT20_DRYRUN=NOT_RUN; P03_T=NOT_RUN`.


## Third batch, 20 targets (offsets 20–39) NAS dry-run — 2026-10-30 KST, user terminal

- Executed from CT108 over SSH as ordinary NAS user `ssikgun`, staged files under `/tmp/p03h-bulk104-sIzAT42z`.
- Script SHA-256 `14a9b65fe87768d8c27598d7a88bb7352aa26fdb6cadcf81f1fcbee570e81cef` PASS; immutable 188-candidate manifest SHA-256 `87ff398ba60f7b062fd07152c82aa3696fe7c8746cbbf530d206f8d51540e087` PASS.
- Command: `python3 -B p03h_bulk104_ssikgun_controlled.py --dry-run --start 20 --count 20`.
- Exact BATCH_IDS: `DVMM-015,EBWH-090,EBWH-296,EKDV-826,EROFV-313,EROFV-387,EROFV-390,FC2-PPV-4973050,FNS-244,FSDSS-901,FTHT-361,FTHTD-219,FTHTD-228,FTKD-045,GANA-3432,HMN-890,HMN-904,HNBR-014,HODV-22112,HODV-22113`.
- User output confirmed `TARGETS_104=PASS; EXCLUDE_MARR014=YES; EXCLUDE_ADMIN83=YES`, `BATCH_START=20; BATCH_COUNT=20`, `PREFLIGHT=20_PASS`, `DRY_RUN=PASS; NAS_WRITE=0 DB_WRITE=0 JELLYFIN_WRITE=0`.
- Standing user approval for 187 exact title-only NFO changes includes this bounded group; exclude the already completed first 20, MARR-014, 59 protected and 83 admin-owned targets. Existing verified runner enforces 20 max. No code changes, no ACL policy change.
- **Third batch LIVE APPLY NOT RUN** at checkpoint. Next one checkpoint is exact script+manifest SHA verification then `--apply --start 20 --count 20 --confirm P03H-104` under normal `ssikgun` user; record full result and backup directory before further actions. On failure stop and inspect, never blindly retry. Then independently verify backup and live NFO/ACL before moving to offset 40.
- No Jellyfin rescan, Stage9 timer changes, other service, video or DB changes observed in this dry-run.

LATEST_STATUS: `FIRST20_INDEPENDENT_POSTCHECK=PASS_20; THIRD20_DRYRUN=PASS_20; THIRD20_APPLY=NOT_RUN; APPLIED_TOTAL=20_OF_187; REMAINING_104=84; LIVE_83=BLOCKED; P03_T=NOT_RUN`.


## Third batch live NFO apply, offsets 20–39 — 2026-10-30 23:48 KST (user CT108/NAS log)

- Exact execution: non-sudo `ssikgun` on NAS, from CT108 SSH, `python3 -B p03h_bulk104_ssikgun_controlled.py --apply --start 20 --count 20 --confirm P03H-104`, staging `/tmp/p03h-bulk104-sIzAT42z`.
- Exact script SHA-256 `14a9b65fe87768d8c27598d7a88bb7352aa26fdb6cadcf81f1fcbee570e81cef` and manifest SHA-256 `87ff398ba60f7b062fd07152c82aa3696fe7c8746cbbf530d206f8d51540e087`: checked `OK` on NAS.
- Protected scope: `TARGETS_104=PASS`, `EXCLUDE_MARR014=YES`, `EXCLUDE_ADMIN83=YES`, `PREFLIGHT=20_PASS`.
- `BATCH_BACKUP=PASS`, exact NAS backup directory `/volume1/video/video2/downloads/backups/stage9/p03h-bulk104-20261030-234831-wfbw63iw`. Preserve originals, ACL receipts and backups.
- `BATCH=PASS; APPLIED_COUNT=20`, `NAS_NFO_WRITE=20; VIDEO_WRITE=0 DB_WRITE=0 JELLYFIN_WRITE=0`, `JELLYFIN_REFRESH=NOT_RUN`.
- Exact applied NFO identities and reported postwrite SHA-256:
  - `DVMM-015`: `e0cf015545aa1e235f8956905b1775d82b75d54f7bb59be241e3831e74100722`
  - `EBWH-090`: `0bbb043602b3f8b8f9903b326b4f10f8da5a3327fa7bb34c389d52245df97484`
  - `EBWH-296`: `3aed91a60a1427bf2c218edaca07b649c7e1fd93ee232891f508bcd97c8da7aa`
  - `EKDV-826`: `e9d3df334a985071e022e6ce1585fd6ce30d84d476e2ff352259c3ce9ff0fd8a`
  - `EROFV-313`: `c9c6ed7b1a4e5fd49e8d49ccf89251a2abf9bce49d421989964436d184527573`
  - `EROFV-387`: `b2bab5fda8b3dab65adfe4fc7cffddc28347c155dcb540a790be9e15ac4e3c1e`
  - `EROFV-390`: `f45ec84747349a0d3f053fffcd8ffa08613e49b8e1fb6a8057fbbafe022893f9`
  - `FC2-PPV-4973050`: `9030ad5d3ca856ebc37b7a50905d219e18cc1f61ed758ded1fc252f18d9ad405`
  - `FNS-244`: `24137cd500dc07f6103879fc1cbcc2e876c2c03fcd2e7386bc54b5b267ea2016`
  - `FSDSS-901`: `1503a9496391a5eb076b4c81de342e3c3372bbdb53174a45c140b92899e307ca`
  - `FTHT-361`: `49099a18e8050254381c2dcad7e421f273b38d3b2df2a96c393c1a1c042a8ce3`
  - `FTHTD-219`: `5349f420e2c3747cc852e231395db2f2edb973205ec362e40b36a76131368d27`
  - `FTHTD-228`: `ccbaeb09b8e3f410a950a06e461e95f2799197a98cb6b691515fea41917e7a58`
  - `FTKD-045`: `b184bcca9424cb31f03bcb88725e497b1c163b31046e1d7932c168e4539919d6`
  - `GANA-3432`: `a4093b20a3cd3d02a6bdde4b4f83f04146437b1b24d17c13e6d82bd924dab87f`
  - `HMN-890`: `04d5ad8d783a978d28779dde5b0ab6f0b95ec19578092a2ce10dd4eeb3dad8cf`
  - `HMN-904`: `9f0b441854bff5560a0ed3b124e20f8371fa0021832542c67cfc60d1bfe37930`
  - `HNBR-014`: `5e4f701798466ca4ca043b360f7ee70177dda3be932d7b3c2cc3e167d73eb9dc`
  - `HODV-22112`: `3c5d292a4c65a151deaa2d763b521d40c12ff4caec51fc5d07b0109098f986b6`
  - `HODV-22113`: `cdf1465ae275432d5986748edb4e182a70b84557161995bc5cc1ebd5a67bfc1a`
- These results are user-supplied live output of the bounded script and **are not yet independently reread** after completion.
- First 20 earlier NFOs are independently verified. Current cumulative 40/187 NFOs were applied, **only 20/187 have independent postcheck PASS**. Remaining: 64 `ssikgun` titles, 83 `admin` titles blocked by permissions. MARR-014 and 59 protected excluded.
- **Next checkpoint:** independent read-only verification of all 20 current NFOs against original backup `original.nfo`, `original_acl.txt`, `receipt.json`, immutable manifest, expected title-only prefix, current SHA256, owner/group/mode/inode and ACL/xattrs. No replay/rollback, no next batch, no Jellyfin library refresh until postcheck evidence. Do not interpret in-script postchecks as an independent postcheck.
- Workstream `STG9MEDIA-001`; Stage9 timer remains unchanged; unrelated sources and services not modified as per observed run.

LATEST_STATUS: `THIRD20_APPLY=PASS_20; THIRD20_INDEPENDENT_POSTCHECK=NOT_RUN; CUMULATIVE_APPLIED=40_OF_187; CUMULATIVE_INDEPENDENT_POSTCHECK=20_OF_187; REMAINING_104=64; LIVE_83=BLOCKED; JELLYFIN_REFRESH=NOT_RUN; P03_T=NOT_RUN`.
