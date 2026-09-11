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
- STAGE11_CANARY_ALIGNMENT_CONTRACT_FROZEN
- STAGE11_GENERIC_UNPROJECTABLE_TARGETED_FALLBACK_FIXED

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
- controller smoke 41/41 PASS
- related targeted/Hybrid/ASR/quality-review regression smoke: PASS
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
- real-title alignment evidence basis frozen: JUR-750 / HSODA-104
- generic CANARY_ONLY alignment acceptance contract frozen
- initial real generic one-title canary: RAN ONCE and stopped fail-closed at
  Hybrid quality review
- fixed-commit real canary resume: NOT RUN

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

## Stage11 Canary Alignment Contract — FROZEN

Marker:

`STAGE11_CANARY_ALIGNMENT_CONTRACT_FROZEN`

This is the first real Stage11 controller canary contract only.

- scope: `CANARY_ONLY`
- production global default: **NO**
- title-specific policy: **NO**
- no `JUR-750`/`HSODA-104` title branch or name-based policy split
- ambiguity (`UNRESOLVED`) uses the controller's `ASR_ONLY` fallback
- prefer false `ASR_ONLY` fallback over false Hybrid acceptance
- when more real-title evidence accumulates, reassess a separate production
  policy; do not promote this contract implicitly
- first real `HSODA-104` controller canary: **RAN ONCE; stopped fail-closed at
  Hybrid quality review**
- fixed-commit `HSODA-104` controller resume: **NOT RUN**
- Stage11: **ACTIVE / NOT CLOSED**
- publication: **NO**

### Frozen real evidence

The following two real-title results are the cross-title basis. `selected
anchors` maps to the source policy's `anchor_count`; `candidate anchors` is
reported evidence and is not a separate `AlignmentAcceptancePolicy` field.

| title | candidate anchors | selected anchors | external span ms | ASR span ms | scale | median absolute residual ms | inliers at threshold 1000 ms | ratio |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| JUR-750 | 156 | 75 | 7001618 | 7123178 | 1.017323284 | 214.915 | 71 / 75 | 0.946667 |
| HSODA-104 | 99 | 65 | 3505250 | 3504430 | 1.000021754798 | 117.728246 | 61 / 65 | 0.938462 |

### Frozen policy

The source constructor/signature is the exact seven-field frozen dataclass:

```python
residual_threshold_ms = 1000

policy = AlignmentAcceptancePolicy(
    minimum_anchor_count=40,
    minimum_inlier_count=40,
    minimum_inlier_ratio=0.90,
    maximum_median_absolute_residual_ms=250.0,
    minimum_evidence_span_ms=1800000,
    minimum_scale=0.95,
    maximum_scale=1.05,
)
```

`decide_alignment_acceptance` evaluates anchor count, inlier count, external
evidence span, and ASR evidence span first. It then evaluates inlier ratio,
median absolute residual, and scale. A quality failure is
`REJECT_EXTERNAL` with `ASR_ONLY` recommended provenance; an insufficient or
ambiguous evidence result is preserved as `UNRESOLVED` for reporting and the
controller route falls back to `ASR_ONLY`.

Arithmetic/static validation at `residual_threshold_ms=1000`:

- JUR-750: anchor count PASS; inlier count PASS; inlier ratio PASS; median
  residual PASS; external/ASR evidence span PASS; scale PASS.
- HSODA-104: anchor count PASS; inlier count PASS; inlier ratio PASS; median
  residual PASS; external/ASR evidence span PASS; scale PASS.

This policy is a handoff contract, not a source-level production policy
constant.

### Next-run values and exact source API map

The next checkpoint must use these explicit canary values. The existing
artifact/staging roots below came from the initial failed canary and must be
preserved for the fixed-commit resume:

- SubtitleCat proxy: `http://127.0.0.1:58888`
- `remote_task_root`:
  `/home/teddy/.hermes/profiles/subtitle-translator/stage11-controller-canary-v1`
- scope: `CANARY_ONLY`
- Discovery DB explicit injection:
  `/opt/missav-dlp-web/discovery/teddy-discovery.sqlite3`
- `request_timeout_seconds`: `1200` (`CANARY_ONLY`)
- `claim_token`: `1` (`STANDALONE_CANARY_ONLY`)
- `artifact_root`:
  `/opt/missav-dlp-web/discovery/stage11-canary-artifacts`
- `stateful_staging_root`:
  `/opt/missav-dlp-web/discovery/stage11-canary-staging`
- initial failed-canary artifact/staging state: **EXISTING; PRESERVE**
- fixed-commit resume must not delete or overwrite the existing canary state

The complete next-run constructor/call map, validated against the current
source signatures, is:

```python
from teddy_discovery_alignment_acceptance import AlignmentAcceptancePolicy
from teddy_discovery_stage11_controller import run_one_title_stage11
from teddy_discovery_stage11_deployment import (
    Stage11DeploymentConfig,
    build_stage11_deployment_dependencies,
)
from teddy_discovery_stage11_live_adapters import build_holding_resolver

config = Stage11DeploymentConfig(
    nas_host="192.168.1.201",
    nas_user="ssikgun",
    nas_key="/opt/missav-dlp-web/teddy-nas-transfer/id_ed25519",
    nas_known_hosts="/opt/missav-dlp-web/teddy-nas-transfer/known_hosts",
    nas_library_root="/volume1/video/video2/JAV",
    asr_base_url="http://192.168.1.134:8091",
    request_timeout_seconds=1200,
    remote_host="192.168.1.230",
    remote_user="teddy",
    ssh_key="/root/.ssh/id_ed25519_stage11_hermes",
    known_hosts="/root/.ssh/known_hosts_stage11_hermes",
    remote_task_root=(
        "/home/teddy/.hermes/profiles/subtitle-translator/"
        "stage11-controller-canary-v1"
    ),
    expected_profile_name="subtitle-translator",
    subtitlecat_timeout_seconds=20.0,
    subtitlecat_proxy_url="http://127.0.0.1:58888",
)

policy = AlignmentAcceptancePolicy(
    minimum_anchor_count=40,
    minimum_inlier_count=40,
    minimum_inlier_ratio=0.90,
    maximum_median_absolute_residual_ms=250.0,
    minimum_evidence_span_ms=1800000,
    minimum_scale=0.95,
    maximum_scale=1.05,
)

deps = build_stage11_deployment_dependencies(
    config,
    acceptance_policy=policy,
    residual_threshold_ms=1000,
    holding_resolver=build_holding_resolver(
        environ={
            "TEDDY_DISCOVERY_DB":
            "/opt/missav-dlp-web/discovery/"
            "teddy-discovery.sqlite3"
        }
    ),
)

run_one_title_stage11(
    "HSODA-104",
    artifact_root=(
        "/opt/missav-dlp-web/discovery/"
        "stage11-canary-artifacts"
    ),
    stateful_staging_root=(
        "/opt/missav-dlp-web/discovery/"
        "stage11-canary-staging"
    ),
    claim_token=1,
    **deps.controller_kwargs(),
)
```

The map is recorded for the next checkpoint only and was not executed in this
freeze.

## Stage11 Generic HYBRID Targeted Evidence Wiring Fix — FROZEN

Marker:

`STAGE11_GENERIC_HYBRID_TARGETED_EVIDENCE_WIRING_FIXED`

The first real `HSODA-104` controller canary reached baseline ASR, targeted
second evidence, and the HYBRID first pass: 204 cues across 13/13 completed
parts. It then stopped fail-closed while building the quality review request
with:

`QualityReviewError: targeted second-evidence binding is detached from Hybrid review cues`

Root cause: the controller HYBRID branch passed the validated targeted
artifact to quality review but did not pass `targeted_bindings` to
`prepare_stateful_hybrid(...)`. The preparation therefore used its default
empty targeted binding tuple even though the review projection had targeted
evidence.

The generic fix is:

`validated targeted windows → existing build_targeted_asr_bindings(...) → deterministic tuple → prepare_stateful_hybrid(targeted_bindings=...)`

No title-, cue-, or text-specific production logic was added. The existing
detached/stale targeted-evidence checks, duplicate semantic ownership rejection,
source identity and plan-binding validation, and the quality-review detached
evidence guard remain fail-closed. ASR_ONLY behavior, alignment acceptance
policy, and residual threshold are unchanged. Existing canary artifacts,
staging, and remote session state are preserved.

- fixed-commit real `HSODA-104` controller resume: **NOT RUN**
- Stage11/R6: **ACTIVE / NOT CLOSED**
- publication: **NO**

Next step: using the frozen fixed commit, perform one real controller resume
while preserving the existing failed-canary artifacts/session.

## Stage11 Generic Unprojectable Targeted Evidence Fallback — FROZEN

Marker:

`STAGE11_GENERIC_UNPROJECTABLE_TARGETED_FALLBACK_FIXED`

### First real canary history and forensic root cause

The first real `HSODA-104` canary generated and durably reused the baseline
and targeted evidence artifacts. Its Hybrid first pass completed 204 cues over
13/13 parts. Quality review then failed closed because the targeted evidence
was unmapped to the Hybrid review cues:

`QualityReviewError: targeted second-evidence binding is detached from Hybrid review cues`

Forensic conclusion: the valid targeted ASR source evidence did not have a
deterministic association to an accepted external-JA cue in its window. The
existing quality-review detached-evidence guard correctly rejected the
unprojectable evidence. This was an identity-domain/projectability condition,
not a title-specific failure.

The `f91a1f7` generic targeted wiring remains in place:

`validated targeted windows → build_targeted_asr_bindings(...) → deterministic tuple → prepare_stateful_hybrid(targeted_bindings=...)`

### Frozen controller contract

- `VALID + all targeted sources projectable → HYBRID`
- `VALID + any targeted source unprojectable or partial → ASR_ONLY`
- `INVALID / DETACHED / STALE → fail-closed`
- no partial targeted projection and no silent targeted-evidence drop
- accepted external alignment verdict/evidence remains immutable on fallback
- quality-review detached-targeted-evidence guard remains unchanged
- `build_targeted_asr_bindings()` remains unchanged and is the association authority
- no title-, cue-, or text-specific production logic
- existing ASR_ONLY path remains the fallback execution path

The controller completeness check compares every validated targeted artifact
binding with the resulting Hybrid semantic targeted binding using exact window,
source-snapshot, and segment identity, requiring a complete one-to-one source
set. It performs no ordinal, nearest-cue, or arbitrary association.

Offline validation: controller smoke 41/41 PASS; targeted Hybrid, targeted
projection, targeted artifact/runner, ASR source-quality, ASR-only review,
stateful Hybrid, and quality-review regression smokes PASS. `py_compile` and
`git diff --check` PASS.

- real `HSODA-104` controller resume after this fix: **NOT RUN**
- Stage11/R6: **ACTIVE / NOT CLOSED**
- publication: **NO**

Next step: using the frozen fixed commit, perform one real `HSODA-104`
controller resume while preserving the existing canary artifacts, staging, and
remote session state.

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
- initial failed canary remote Hermes/VM122/Whisper calls: completed before the
  quality-review stop
- fixed-commit resume remote Hermes/VM122/Whisper calls: NOT RUN
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
- fixed-commit `run_one_title_stage11` real-canary resume

이 항목들은 필수 구현 결함으로 과장하지 않는다. 현재 다음 milestone에서
필요한 것만 구분한다.

## Next Step

production connection values read-only preflight
→ one fixed-commit real generic `run_one_title_stage11` canary resume

첫 canary는 QualityReviewError에서 fail-closed 되었고, fixed-commit resume는
아직 실행하지 않았다.

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
