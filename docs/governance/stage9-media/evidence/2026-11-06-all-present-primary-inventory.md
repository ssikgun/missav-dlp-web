# Stage9 Media — 2026-11-06 full NAS-primary inventory evidence

Source: user-executed `root@downloader` CT108 output. Workstream: `STG9MEDIA-001`, approved Stage9 Media contract v1.0.9. This is a read-only inventory report, not approval to create or replace images or to start a service.

Exact scope: 260 distinct `holdings WHERE present=1 AND storage_root='jav'`, SQLite `mode=ro` / `PRAGMA query_only=ON`. One SSH call inspected the exact DB-recorded NAS movie folders, validated directory/video type and size, and classified recognized NAS-local Primary image names (`poster`, `cover`, `folder`, `default`, `movie`; JPEG/PNG/WebP) by regular-file presence. No recursive NAS library scan. Console: `DB_PRESENT_JAV=260`, `CHECKED=260`, `NAS_FILE_WRITES=0`, `MEDIA_RUNNER_EXECUTIONS=0`, `ALL_HOLDINGS_INVENTORY=COMPLETE`.

| Source | Present holdings | Primary PRESENT | Primary MISSING | HOLD |
| --- | ---: | ---: | ---: | ---: |
| completion-stage9 | 131 | 119 | 12 | 0 |
| library-inventory | 68 | 38 | 30 | 0 |
| organizer-apply | 61 | 48 | 13 | 0 |
| **Total** | **260** | **205** | **55** | **0** |

Interpretation: `MISSING=55` is absence of a recognized NAS-local image file in the exact movie folder; it is NOT proof that Jellyfin currently shows no representative image or that a usable poster URL exists. HOLD=0 is a result of this read-only path/size/name inspection, not full publication eligibility. Revalidate current holdings and local Primary at write time.

## Exact missing IDs from CT108 report

### completion-stage9 — 12

- `FC2-PPV-4982148`
- `FC2-PPV-4983582`
- `GANA-3223`
- `LUXU-1725`
- `MAAN-945`
- `MBRBI-015`
- `MFCS-085`
- `MIUM-1406`
- `NHDTB-778`
- `NTR-102`
- `PRIAN-059`
- `PRIAN-060`

### library-inventory — 30

- `FC2-PPV-4551303`
- `FC2-PPV-4592689`
- `FC2-PPV-4640215`
- `FC2-PPV-4696030`
- `FC2-PPV-4722815`
- `FC2-PPV-4758058`
- `FC2-PPV-4778191`
- `FC2-PPV-4783033`
- `FC2-PPV-4783149`
- `FC2-PPV-4783151`
- `FC2-PPV-4783157`
- `FC2-PPV-4783446`
- `FC2-PPV-4783822`
- `FC2-PPV-4784721`
- `FC2-PPV-4784880`
- `FCT-198`
- `FCT-201`
- `FCT-203`
- `FCT-204`
- `MFC-355`
- `MFCS-198`
- `MFCW-068`
- `NHDTB-93803`
- `ORECO-754`
- `SGKI-075`
- `SIRO-3917`
- `SIRO-4381`
- `SIRO-4448`
- `SIRO-5536`
- `SIRO-5537`

### organizer-apply — 13

- `FC2-PPV-4555371`
- `FC2-PPV-4575470`
- `FC2-PPV-4660439`
- `FC2-PPV-4778984`
- `FC2-PPV-4795461`
- `FC2-PPV-4960750`
- `FCT-188`
- `FCT-205`
- `HRSM-087`
- `HUNTC-513`
- `MAAN-869`
- `MFC-258`
- `SW-216`

## Protection and next action

- The 205 PRESENT titles must remain protected from competing or overwritten local Primary files.
- `MBRBI-015` is in the missing group but has a previously protected Jellyfin Primary/backup history. Keep it OUT of generic bulk artwork APPLY until its special protection and explicit permission are confirmed.
- `GANA-3223` had previous NFO completion / poster pending; do not rerun/overwrite the NFO or modify historic job state merely due to this list.
- AT-099 and the three 2026-11-05 image canaries already passed and are not missing here; do not reprocess.
- 43 of 55 belong to legacy `library-inventory`/`organizer-apply` holdings; current automatic `reconcile_media_jobs` only starts from completion-stage9 holdings. Do not assume enabling the Stage9 timer repairs legacy files.
- Next: bounded full 55-title preflight, then separate operational approval for sequential exact-target, create-only missing-image processing. Maintain one title per `--thumbnail-only --existing-image-only` invocation and no forced Jellyfin image API write/scan. Automatic new-title Stage9 timer activation is another separate decision.
