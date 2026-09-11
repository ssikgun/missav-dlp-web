# Teddy Downloader / missav-dlp-web Current Handoff

## Current Goal

Stage11 generic Korean subtitle generation pipeline completion and first real
one-title end-to-end canary preparation.

## Overall Status

- Stage0–10 CLOSED / PASS
- Stage11 ACTIVE
- Stage12 NOT STARTED
- R6 ACTIVE
- STAGE11_SUBTITLECAT_PROXY_WIRING_FROZEN

## Completed

- external JA discovery/validation
- affine alignment and safe Hybrid acceptance
- STT-only fallback path
- GPU large-v3 baseline ASR
- durable baseline ASR artifact
- generic ASR source-quality classifier
- targeted second-evidence V1 windows
- targeted GPU/remote path
- durable targeted evidence artifacts
- cross-title calibration: ADN-785 / HSODA-104 / DVDMS-117
- structural/runaway repetition must NOT directly imply OMIT
- generic second-pass evidence projection
- ASR-only + Hybrid stateful semantic review
- deterministic CLEAN materialization
- generic empty Whisper word normalization
- thin generic `run_one_title_stage11(...)` controller
- controller smoke 30/30 PASS
- related regression 26 smoke groups PASS
- `build_stage11_live_dependencies(...)` factory
- Flask-free existing-config holding resolver adapter
- first-pass native `run(Namespace)` adapter
- ASR review fresh-session adapter
- Hybrid review fresh-session adapter
- targeted runner source-snapshot adapter
- baseline transcriber composition adapter
- external JA discovery/provider/alignment adapter
- controller + live adapters fake E2E: ASR_ONLY PASS / HYBRID PASS
- `build_stage11_deployment_dependencies(...)` deployment factory
- Flask-free holding resolver using the existing discovery DB contract
- deployment-owned deterministic remote task/session wiring
- CT120 native first-pass preparation and review launcher bridges
- Hybrid originals projection from retained native evidence
- bounded SubtitleCat detail/payload transport composition
- VM122 request timeout `1200` accepted as CANARY_ONLY explicit input
- standalone canary `claim_token=1` retained as STANDALONE_CANARY_ONLY
- deployment + live adapters fake E2E: ASR_ONLY PASS / HYBRID PASS
- deployment smoke: 17/17 PASS
- explicit SubtitleCat-only Gluetun proxy wiring
- search, detail, and payload use the same configured SubtitleCat proxy
- proxy `http://127.0.0.1:58888` is not a global HTTP proxy
- SubtitleCat proxy offline smoke: PASS
- actual Hermes/VM122/Whisper calls: NO
- first real generic one-title canary: NOT RUN

## Current Architecture

Generic flow:

TITLE
→ canonical holding
→ baseline ASR
→ external JA attempt
→ safe HYBRID else ASR_ONLY
→ source-quality
→ REQUIRE-only targeted second evidence
→ stateful first-pass translation
→ semantic second-pass review
→ deterministic CLEAN
→ local mechanical report
→ STOP

No automatic publication.

## Frozen Policies

- production title/cue/text hardcode 금지
- external JA and Whisper are both fallible
- safe accepted external JA only for Hybrid
- no candidate/fetch/validation/REJECT/UNRESOLVED:
  controller-level ASR_ONLY fallback
- internal invariant/provenance mismatch: fail-closed
- false OMIT worse than uncertain KEEP
- AMBIGUOUS deterministic KEEP
- targeted evidence is evidence only
- Hermes does not own timing, identity, or publication
- no automatic NAS overwrite
- no Jellyfin DB write
- publisher excluded from default controller
- `/var/tmp` artifacts are calibration-only, not production defaults
- SubtitleCat search/detail/payload may use only the explicit deployment proxy;
  NAS, VM122, Hermes, and Discovery DB routing are unchanged

## Cross-title Calibration

ADN-785:

- baseline 921
- REQUIRE 4
- lexical/noisy/reaction mixed

HSODA-104:

- baseline 265
- REQUIRE 1
- targeted lexical recovery

DVDMS-117:

- baseline 491
- REQUIRE 2
- targeted lexical recovery
- baseline SHA:
  `5fc3f814162f0152871136bc2901653b574179d85ca050983342994849f7e261`
- targeted SHA:
  `74390dd3a836fd95ba275e1f45f4039d2adbbecfc5f86d8d54f900fec31f6e71`

Cross-title conclusion:

CROSS_TITLE_CALIBRATION_SUFFICIENT

## VM122 Current Worker

- host 192.168.1.134
- port 8091
- endpoint `/v1/asr/transcribe`
- endpoint `/v1/asr/transcribe-targeted`
- model large-v3 / CUDA / float16
- empty-word generic normalization active
- latest deployed gpu worker SHA:
  `ddb39a490d0a44a04d72b51293dea541dc7be4ab212b083fa5b16b336358f927`

## Controller Runtime Contract

- title = canonical DVD-ID only
- artifact_root = explicit caller input
- stateful_staging_root = explicit caller input
- TEDDY_DISCOVERY_DB existing config owner
- valid existing artifact → reuse
- absent → generate
- invalid/detached → fail-closed
- REQUIRE=0 → targeted call 0
- valid targeted artifact → reuse
- CLEAN + report is normal stop point
- publication_performed=false

## Important Runtime Paths

CT108 worktree:

`/opt/missav-pwa-subtitle-stage11`

Discovery DB:

`/opt/missav-dlp-web/discovery/teddy-discovery.sqlite3`

VM122 live worker source:

`/home/teddy/stage11-asr-worker-dcc835a`

Hermes profile:

`/home/teddy/.hermes/profiles/subtitle-translator`

Hermes state DB:

`/home/teddy/.hermes/profiles/subtitle-translator/state.db`

## Deployment Wiring Status

- production connection values read-only preflight: mostly PASS
- deployment-owned callbacks/config are implemented and offline-smoke validated
- canary timeout `1200`: CANARY_ONLY, not a production module default
- `claim_token=1`: STANDALONE_CANARY_ONLY, not a job allocator
- actual remote Hermes/VM122/Whisper calls: NOT RUN
- publication: NOT PERFORMED

## SubtitleCat Network Route

- CT108 direct egress `39.118.143.206`: HSODA-104 search returned HTTP 500
- Gluetun VPN egress `169.150.197.108`: SubtitleCat search returned HTTP 200
- canary proxy endpoint: `http://127.0.0.1:58888`
- Gluetun compose mapping: `127.0.0.1:58888 -> 8888/tcp`
- search, detail page, and subtitle payload share the explicit SubtitleCat-only
  proxy configuration
- global `HTTP_PROXY`, `HTTPS_PROXY`, and `ALL_PROXY` are not configured by
  Stage11

## Unresolved / Not Yet Provisioned

- production Stage11 artifact root
- Stage11 jobs DB
- production staging root
- external JA/alignment durable reuse store
- first real `run_one_title_stage11` real canary

이 항목들은 필수 구현 결함으로 과장하지 않는다. 현재 다음 milestone에서
필요한 것만 구분한다.

## Next Step

production connection values read-only preflight
→ first real generic `run_one_title_stage11` one-title canary

아직 실제 canary 실행 전이다.

## New Conversation Warnings

- Stage11 CLOSED 선언 금지
- Stage12 시작 금지
- 작품별 튜닝으로 되돌아가지 않기
- ADN/JUR/HSODA/DVDMS 특정 production logic 금지
- old canonical KO subtitle overwrite 금지
- no blind retries
- no broad NAS scan
- no automatic publication
- controller/result가 timing authority를 Hermes에 넘기지 않도록 유지
