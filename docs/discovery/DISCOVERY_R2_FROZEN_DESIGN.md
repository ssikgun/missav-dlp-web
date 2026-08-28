# Teddy Downloader — Discovery R2 FROZEN Design

**Design ID:** `TEDDY-DISCOVERY-R2-FROZEN-V1-20260828`

**Status:** FROZEN

**Frozen on:** 2026-08-28

**Source branch at freeze:** `teddy-discovery-stage5`

**Pre-freeze source HEAD:** `d3f08b71c155cf69abc05957711902017836fcde`

---

## 1. Authority

This document is the canonical design contract for Discovery R2.

Implementation must follow this document.

If implementation pressure, a later discovery, or a convenience refactor conflicts
with this document, implementation must stop and this document must be explicitly
reviewed before the design is changed.

Do not silently reinterpret, weaken, or bypass a frozen rule.

Stage 6 Organizer work remains on HOLD until all pre-Stage6 Discovery R2 work is
explicitly completed.

---

## 2. Core product model

Discovery R2 is a persistent JAV release catalog and discovery database.

The database permanently accumulates catalog data.

The UI's recent seven-day view is only a presentation window.

It is not a retention window.

Older catalog rows must not be deleted merely because they are outside the recent
seven-day UI window.

External sites are collectors and enrichment sources.

They are not the UI's direct source of truth after ingestion.

The Teddy Discovery DB is the catalog source of truth after ingestion.

---

## 3. Release Calendar

### Required behavior

`release_date` means the official catalog release date.

Existing title `first_seen_at` semantics remain Teddy's first discovery time.

The main Release Calendar view shows the most recent seven release dates.

The upper-right date selector allows the user to select one of those dates.

For the selected date, the UI must show all catalog titles for that date.

There must not be a 50-title data truncation for a selected release date.

Future titles may be stored in the DB before release.

They do not appear in the recent released-date view until their release date is
reached.

The seven-day UI view must not affect permanent DB retention.

---

## 4. Release and catalog source roles

No single external source is treated as the complete permanent catalog.

### FANZA via javinfo / RapidAPI

Role:

- future-release seed
- scheduled-title discovery
- optional metadata prefetch

Confirmed behavior:

- release ordering works
- provider deep pagination is bounded
- it is not sufficient as the Recent 7-day source of truth by itself

RapidAPI must be used under a bounded monthly budget.

Operational target:

- keep normal use below approximately 80 requests per month
- retain quota safety margin
- do not perform wasteful daily full sweeps

### RapidAPI providers rejected for Recent Calendar

`javdb`:

- live page 1 returned HTTP 404
- not usable

`javdatabase`:

- live provider works
- `sort=release` does not provide globally descending release ordering
- not usable as authoritative Release Calendar ordering

`missav` RapidAPI provider:

- tested date-window variants returned HTTP 404
- not used as Recent Calendar source

### JAV Database direct

Keep as a strong rich-metadata source.

Do not treat `/movies/page/N/` pagination as a globally release-date-sorted
enumeration source.

Existing direct movie metadata behavior remains preferred where already proven.

### MissAV family

MissAV-family discovery remains an important real availability and download source
and catalog supplement.

Logical source identity remains:

`missav`

Physical mirrors are a separate concern.

---

## 5. MissAV physical source policy

The preferred physical MissAV host for R2 download and availability work is:

`missav123.com`

Other MissAV mirrors remain members of the same logical MissAV family.

Examples:

- `missav123.com`
- `missav01.com`
- `missav.ws`

`canonical_site(...)` must continue to treat these as logical source:

`missav`

Do not create separate logical source identities for individual MissAV mirrors.

---

## 6. 123AV policy

123AV is fallback-only.

It must not be probed or selected as an equal primary peer when a valid MissAV-family
file is already confirmed for the same title.

Frozen source priority:

1. confirmed uncensored MissAV-family variant
2. standard MissAV-family file
3. 123AV only when the MissAV family is unavailable
4. unavailable / fail closed

If MissAV standard is available and 123AV has an uncensored copy, the default still
remains MissAV-family according to this fallback policy.

---

## 7. Uncensored variant semantics

A generic occurrence of the word `uncensored` on a page is not sufficient.

A variant is confirmed uncensored only when the uncensored signal belongs to a URL,
href, filename, or variant slug that resolves to the same canonical DVD ID.

The uncensored token must be separator-aware.

`leak` alone is not an uncensored signal.

Generic page text is not an ownership signal.

Example:

DVD ID:

`SW-893`

Variant slug:

`sw-893-uncensored-leak`

Variant page:

`https://missav123.com/ko/sw-893-uncensored-leak`

Existing `parse_dvd_id()` is the canonical DVD-ID normalizer.

Do not create a second competing DVD-ID parser for variants.

Proven inputs include:

- `sw-893`
- `sw-893-uncensored-leak`
- `[sw-893-uncensored-leak] SW-893 title.mp4`
- `https://missav123.com/ko/sw-893-uncensored-leak`

All resolve to canonical DVD ID:

`SW-893`

---

## 8. Variant data model

Existing `titles`, `latest_items`, and `availability` tables do not safely model
multiple downloadable variants of the same logical title.

R2 introduces a dedicated variant entity.

Target schema version:

`6`

Target table:

`title_variants`

Minimum frozen semantics:

- `dvd_id`
- `source`
- `variant_kind`
- `variant_slug`
- `page_url`
- `confirmed`
- `first_seen_at`
- `last_seen_at`
- `last_checked_at`

Initial frozen variant kinds:

- `standard`
- `uncensored`

Recommended logical key:

`(dvd_id, source, variant_kind)`

`page_url` must not ambiguously belong to multiple logical variants.

Do not overload `titles.metadata_source`.

Do not repurpose `latest_items.source_url` as the persistent variant store.

Do not overload the existing `(dvd_id, source)` availability row to represent
multiple MissAV variants.

---

## 9. Browser and API trust boundary

The browser continues to send only:

~~~json
{"dvd_id":"SW-893"}
~~~

The Discovery download endpoint must remain strict and fail closed for extra
upstream-control fields.

Do not expose or accept browser-controlled:

- `page_url`
- `source_url`
- `variant_url`
- arbitrary upstream URL
- arbitrary provider selection

The browser must not construct upstream download URLs.

Variant and source resolution are server-side responsibilities.

---

## 10. Download resolver

The server resolves the actual page URL internally.

Frozen resolution order:

1. load canonical DVD ID
2. check for a confirmed MissAV uncensored variant
3. if present, select its server-stored page URL
4. otherwise select standard MissAV-family URL when available
5. only when MissAV family is unavailable, use confirmed 123AV fallback
6. otherwise fail closed

The resolver must pass the resolved URL through the existing guarded enqueue,
routing, and downloader path.

Do not create a second downloader engine for uncensored variants.

---

## 11. Existing Downloader engine

Existing `MyCustomMissAV` remains the MissAV-family extraction engine.

It already accepts MissAV mirror URLs including `missav123.com`.

Live extraction-only proof confirmed that:

`https://missav123.com/ko/sw-893-uncensored-leak`

was accepted by the existing extractor.

The variant ID remained:

`sw-893-uncensored-leak`

The extractor discovered HLS formats at:

- 360p
- 480p
- 720p
- 1080p

No media-file download was required for this proof.

Therefore:

**Do not rewrite the MissAV download engine for R2 variant support.**

The required R2 change is upstream variant resolution, not a new media engine.

---

## 12. Duplicate identity

Current generic MissAV duplicate keys distinguish:

`missav:sw-893`

from:

`missav:sw-893-uncensored-leak`

That is not the desired Discovery R2 title-level behavior.

Discovery must treat standard and uncensored variants of the same canonical DVD ID
as the same logical title for queue-duplication purposes.

Do not globally rewrite generic URL duplicate behavior unless separately justified.

Prefer a Discovery-specific canonical DVD-ID duplicate boundary.

Use existing `parse_dvd_id()` to obtain canonical identity.

Desired Discovery duplicate identity example:

`SW-893`

If a standard SW-893 task is active, discovering an uncensored variant later must
not silently enqueue a second concurrent SW-893 task.

If a confirmed uncensored variant already exists when the user initiates the
download, the resolver should choose the uncensored variant before task creation.

---

## 13. UI uncensored badge

Display an uncensored badge only for confirmed title-owned uncensored variants.

Unknown, inferred, generic text-only, or unowned signals must not receive the badge.

The badge is a statement about a confirmed downloadable variant.

It is not a statement derived from arbitrary metadata text.

---

## 14. Availability model direction

R2 availability must align with the frozen source policy.

Primary availability is MissAV-family availability, with preferred physical probing
against `missav123.com`.

123AV is not an equal parallel probe.

123AV should be probed as fallback when the MissAV family is unavailable.

Avoid the old cost pattern of automatically probing both sources for every title.

Availability priority should approximately be:

1. released today and unconfirmed
2. recent seven-day releases
3. near-future releases approaching release
4. older NOT_FOUND / UNKNOWN retries

FOUND rows should not be wastefully rechecked at high frequency.

Backoff and fail-closed behavior remain required for negative or uncertain states.

---

## 15. Refresh cadence direction

R2 should not depend on one giant nightly refresh.

Frozen direction:

### Release discovery

Approximately every 4 hours.

Purpose:

- reduce risk of missing transient newly listed titles
- keep the Release Calendar timely

### Metadata enrichment

Small bounded batches approximately every 2 to 3 hours.

Do not keep a throughput model that permanently accumulates metadata backlog under
normal observed discovery volume.

### Availability

Approximately every 2 to 3 hours using explicit priority.

Do not spend equal requests on 123AV when MissAV family is already confirmed.

### Weekly ranking

JAV Database weekly ranking may remain approximately daily.

### Monthly and category

Continue local derivation from stored data where already designed.

---

## 16. Permanent accumulation

Catalog rows are retained.

External pagination windows must not cause older Teddy catalog entries to disappear.

If a provider later stops returning a title because that title aged out of the
provider's pagination window, the Teddy DB still retains that title.

Provider disappearance is not a deletion signal.

---

## 17. Existing metadata and source boundaries

Keep the existing proven metadata preference behavior unless explicitly revised.

JAV Database direct movie metadata remains strong.

MissAV English movie parsing remains a verified fallback where already designed.

Metadata source identity and downloadable-variant identity are separate concepts.

Do not conflate:

- metadata source
- release discovery source
- availability source
- physical mirror
- downloadable variant

---

## 18. Stage 6 and Stage 7 boundary

Stage 6 Organizer remains HOLD during Discovery R2 implementation.

The existing untracked Organizer prototype files remain untouched:

- `teddy_discovery_organizer.py`
- `teddy_discovery_organizer_smoke.py`

Actual media-file moves do not begin as part of R2 work.

Stage 7 publish semantics remain a later separate boundary.

---

## 19. Evidence checkpoints behind this freeze

Important proven checkpoints include:

- CP47 — owned uncensored variant detection
- CP53 — live FANZA RapidAPI query
- CP54 / CP54R-A — FANZA pagination boundary
- CP55 — RapidAPI `javdb` unusable
- CP56 / CP57 — `javdatabase` live but release sort not authoritative
- CP58 — RapidAPI MissAV provider date-window requests unusable
- CP59 / CP59R-A / CP59R-B — Discovery download front door and extractor-entry contract
- CP60 — live SW-893 uncensored extraction-only success
- CP61 — DB schema and duplicate-key forensic
- CP62 / CP62R-A — canonical DVD-ID variant normalization and migration boundary

---

## 20. Implementation order after freeze

Implementation proceeds incrementally.

### Phase A

Schema v5 -> v6.

Add `title_variants`.

Add deterministic offline migration, storage, and readback smoke tests.

No Production DB write.

### Phase B

Variant collector and ownership classifier.

No browser URL trust expansion.

### Phase C

Server-side variant resolver.

Keep browser `dvd_id`-only contract.

### Phase D

Discovery-specific duplicate identity.

Do not broadly rewrite unrelated URL duplicate behavior.

### Phase E

UI badge and Release Calendar recent-seven-date presentation.

No 50-row selected-date truncation.

### Phase F

Refresh and availability cadence changes.

Only after source and resolver semantics are stable.

### Phase G

Production rollout with separate explicit checkpoints.

---

## 21. MUST NOT list

R2 implementation MUST NOT:

- expose upstream page URLs to the browser for download selection
- accept browser-supplied variant URLs
- make 123AV an equal primary source
- prefer 123AV uncensored over an available MissAV-family standard file by default
- infer uncensored from generic page text
- treat `leak` alone as uncensored
- create a second DVD-ID normalization implementation
- rewrite the existing MissAV media engine merely to support variants
- use RapidAPI `javdatabase` as authoritative release ordering
- use RapidAPI `javdb` as a live release source
- use RapidAPI MissAV as the Recent Calendar source
- delete old catalog rows because an external provider stopped returning them
- cap a selected release date to 50 titles
- start Stage 6 Organizer work during R2
- modify or commit the two held Organizer prototype files as part of R2
- physically duplicate files by actor or genre
- directly edit Jellyfin's database

---

## 22. Change-control rule

This design is FROZEN.

If a future implementation requires changing one of the frozen rules, stop first.

Document:

1. the exact frozen rule being changed
2. new evidence requiring the change
3. blast radius
4. migration and rollback implications
5. updated tests

Then explicitly revise this design document in a dedicated design-change commit before
changing implementation behavior.

No silent drift.
