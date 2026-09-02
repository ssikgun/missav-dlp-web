# Teddy Downloader Discovery — Stage 0~9 Final Handoff + Next Roadmap

- 작성일: 2026-09-02 KST
- 프로젝트: Downloader / Teddy Discovery
- Repository: `ssikgun/missav-dlp-web`
- 현재 개발 브랜치: `teddy-completion-stage9`
- Stage9 기능 commit: `97a35cbb539e5d1dd7ed1f43514cf3634691538c`
- Stage9 최종 구조 commit: `7dbad5aea8c8fb6f5906c1fa136852a1254c93dd`
- 현재 상태: **Stage 0~9 CLOSED / PASS**
- Stage9 Production 실전 E2E: **PASS (`SIRO-5731`)**

---

# 1. 이 문서의 목적

이 문서는 Teddy Downloader의 Discovery / Library / Organizer / Metadata / Jellyfin 흐름을 Stage0부터 현재 Stage9까지 한 번에 이어볼 수 있는 최신 핸드오프다.

이전 Stage8 최종 handoff는 Stage8 이후의 목표를 미리 확정하지 않았고, 다음 Stage를 Teddy와 새로 정의하도록 남겼다. 이번 대화에서 새 Stage9를 **완성된 다운로드 파일의 자동 Organizer + metadata/poster + Jellyfin 연결을 Production에서 지속 실행하는 단계**로 정의하여 구현/검증/배포했다.

주의: 초창기 설계 문서에 적힌 historical `Stage9 = Discovery Download button`, `Stage10 = Production rollout` 번호와 이번 Stage9는 동일한 의미가 아니다. Historical Download button은 Stage5/R2 진행 중 이미 구현 완료되었으므로 재실행하지 않는다.

이 문서를 이후 작업의 최신 handoff로 사용하되, `docs/discovery/DISCOVERY_R2_FROZEN_DESIGN.md`의 frozen invariant와 충돌하면 frozen design을 우선한다.

---

# 2. Teddy와 작업할 때 지켜야 할 방식

## 보고 방식

Teddy가 checkpoint 로그를 붙이면:

1. 첫 visible token은 반드시 `PASS`, `FAIL`, `INCOMPLETE` 중 하나.
2. 긴 로그를 그대로 반복하지 않는다.
3. 쉬운 한국어로 핵심만 설명한다.
4. 한 번에 다음 checkpoint 하나만 제시한다.
5. 가능하면 마지막에 `지금 한 일 / 다음 할 일`을 짧게 정리한다.

## 명령어 제공 방식

명령 블록마다 반드시 실행 위치를 명시한다.

예:

- `PVE Host (root@pve)`
- `CT108 Downloader LXC (root@downloader)`
- `CT112 Media/Jellyfin LXC`

명령은 주기 전에 대상과 문법을 다시 확인한다.

## 변경/삭제 안전 규칙

삭제, purge, destroy, unmount, config-line 제거, 서비스 중단/재부팅, repository 변경, Production DB/NAS/Jellyfin write 등 실제 상태를 바꾸는 작업은 **정확히 무엇을 바꿀지 먼저 Teddy에게 설명하고 승인받은 뒤** 수행한다.

복구/rollback artifact는 별도 승인 없이 삭제하지 않는다.

## Shell 안전

주지 않는다:

- `exit`, `logout`
- interactive `set -e`, `set -eu`, `set -euo pipefail`
- `|| exit 1`
- shell replacing `exec`
- `kill $$`
- naked `false`

실패 제어는 `ok=1`, `ok=0`, `if` 패턴을 선호한다.

## NAS scan 안전

`/mnt/nas-*`, `/mnt/pve/Proxmox_NFS`, NAS root 등에 broad recursive `find`, `rglob`, `du`를 무심코 실행하지 않는다. 과거 HDD 부하 문제가 있었으므로 **정확한 경로 / bounded-depth / DB-known path** 기반으로 확인한다.

---

# 3. 현재 전체 구조

최종 사용자 흐름:

```text
Discovery
  -> 신작 / 주간 / 월간 / 장르
  -> metadata + availability
  -> [다운로드]
  -> 기존 Teddy Downloader
  -> CT108 local download/remux
  -> NAS video2/downloads
  -> Stage9 Completion/Organizer
  -> NAS video2/JAV/PREFIX/DVD-ID/DVD-ID.mp4
  -> NFO + poster
  -> Jellyfin notify/index
  -> Infuse/Jellyfin에서 감상
```

역할 분리:

```text
Discovery DB  = catalog / metadata / ranking / holdings / organizer logical state
NAS filesystem = 실제 media byte source of truth
Stage9 media DB = media sidecar/Jellyfin retry state only
Jellyfin DB = 감상용 media index
Infuse = 감상 client
```

Jellyfin internal DB를 Teddy가 직접 수정하지 않는다.

---

# 4. Production 핵심 경로

## CT108 Downloader

```text
Production runtime:
  /opt/missav-dlp-web

Production compose:
  /opt/missav-dlp-web/compose.yaml

Discovery DB:
  /opt/missav-dlp-web/discovery/teddy-discovery.sqlite3

Discovery writer lock:
  /run/lock/teddy-discovery-r2-writer.lock
```

Discovery DB schema는 **v6 유지**다.

## NAS

```text
NAS IP:
  192.168.1.201

completed download root:
  /volume1/video/video2/downloads

final JAV root:
  /volume1/video/video2/JAV
```

Stage9는 CT108에서 NAS를 broad mount/scan하지 않고 SSH 경계를 사용한다.

## CT112 Jellyfin

```text
Jellyfin:
  http://192.168.1.205:8096

Stage9 container-visible library path:
  /media/adult
```

Jellyfin media mount는 read-only 정책을 유지한다.

---

# 5. Stage별 완료 내용

## Stage 0 — Media / Jellyfin forensic — CLOSED / PASS

실제 NAS, CT112, Jellyfin, Infuse 구조를 확인했다.

확정된 역할:

- `video2/downloads`: 다운로드 완료 후 Organizer 대기 영역
- `video2/JAV`: 최종 library
- Jellyfin Adult library는 JAV만 본다.
- Jellyfin media 접근은 read-only.
- Infuse-Direct 실제 playback 경로 확인.

이 단계에서 향후 Organizer/Jellyfin 경계를 고정했다.

---

## Stage 1 — Discovery DB + 기존 JAV inventory — CLOSED / PASS

구현:

- local SQLite Discovery DB
- schema migration 관리
- authoritative DVD-ID parser
- 기존 JAV library read-only inventory
- `titles`와 `holdings` 분리

초기 inventory 결과:

```text
JAV media files: 69
holdings: 69
matched unique DVD IDs: 69
```

중요 원칙:

- DB의 `titles` 존재와 실제 파일 보유 여부는 별개다.
- 실제 보유 여부는 `holdings.present=1`이 담당한다.
- 품번 parser는 prose 중간의 임의 문자열을 무리하게 품번으로 해석하지 않는다.

---

## Stage 2 — Metadata + Latest — CLOSED / PASS

구현:

- metadata normalization
- MissAV release/latest collector
- pagination
- fixed VPN collector boundary
- title / maker / release date / people / genres / cover metadata

RapidAPI/javinfo는 제한된 rich metadata/future seed 역할로만 사용하고 nightly Latest source로 남용하지 않는 정책을 확정했다.

Teddy Latest는 MissAV의 release semantics를 기준으로 DB에 누적하고, UI는 external site를 매번 직접 읽지 않고 local DB를 읽는다.

---

## Stage 3 — Weekly / Monthly / Category — CLOSED / PASS

구현:

- JAVDatabase weekly ranking snapshot
- local ranking history
- monthly derivation
- category ranking/facet derivation

외부 chart snapshot은 증거로 보존하고, monthly/category는 local DB에서 계산하는 구조로 분리했다.

---

## Stage 4 — Availability — CLOSED / PASS

대상:

- MissAV
- 123AV

상태 모델:

```text
FOUND
NOT_FOUND
UNKNOWN
```

구현:

- cache/backoff
- bounded planner/job
- fixed network boundary
- 기존 값 보존을 우선하는 failure policy

external failure가 Downloader core를 막지 않도록 fail-soft 경계를 유지한다.

---

## Stage 5 — Discovery UI / Preview / Download 연결 — CLOSED / PASS

최종 UI 주요 기능:

- 최신
- 주간 TOP
- 월간 TOP
- 장르
- release date selector
- cover lazy-load
- preview lazy/touched-only
- 한 번에 preview 1개
- availability badges
- 보유/미보유 badge
- Discovery Download button

현재 UI data layer는 이미 `holdings`를 조회하여:

```text
owned = holding_count > 0
holding_count
```

을 반환하고, frontend도 `보유 N / 미보유`를 렌더링한다.

Discovery Download는 새 다운로드 엔진이 아니라 기존 Teddy Downloader queue에 canonical source URL을 전달한다.

현재 download API의 duplicate guard는 **활성 queue에 같은 DVD-ID가 중복 enqueue되는 것**을 막는다.

중요: **이미 library에 보유한 DVD-ID를 다운로드 전에 차단하는 holdings guard는 아직 없다.** 이것은 다음 Stage의 확정 구현 대상이다.

---

## Discovery R2 Production stabilization — CLOSED / PASS

Stage5 이후 R2 frozen design에 맞춰:

- release calendar
- future FANZA seed
- availability scheduling
- variant handling
- sparse metadata policy
- production timers/runner
- deterministic smokes/canaries
- immutable image promotion

등을 정리했다.

Stage8 closure 시 Discovery timers 6개가 active/enabled 상태였다.

---

## Stage 6 — Organizer Dry-run — CLOSED / PASS

목적:

```text
현재 파일
  -> 예정 canonical destination
```

을 먼저 계산하고 실제 media write 없이 collision/ambiguity/metadata readiness를 검증했다.

canonical layout:

```text
JAV/PREFIX/DVD-ID/DVD-ID.mp4
```

filesystem은 DVD-ID 중심으로 단순하게 유지하고 배우/장르별 physical duplication은 하지 않는다.

fail-closed 대상에는 parse ambiguity, destination collision, unsafe path, changing source, holding/filesystem contradiction 등이 포함된다.

---

## Stage 7 — Organizer Apply — CLOSED / PASS

Stage6에서 검증한 후보를 실제 JAV canonical layout으로 적용했다.

안전 경계:

- publish 검증 완료 전 source 삭제 금지
- destination collision fail closed
- DB holding commit과 filesystem state 순서 보장
- Organizer 실패가 completed media 삭제로 이어지지 않음

Stage8 closure 시 기존 library:

```text
holdings: 130
organizer jobs: 130 / 130 COMPLETED
```

---

## Stage 8 — Metadata / NFO / Poster / Jellyfin — CLOSED / PASS

130개 기존 library를 대상으로 metadata backfill, sidecar, Jellyfin integration을 완료했다.

최종 Stage8 핵심:

```text
holdings: 130
organizer COMPLETED: 130
metadata complete: 130
NFO complete: 130
physical poster targets: 85
coverless: 45
coverless fake poster: 0
Jellyfin Movies: 130
Jellyfin Generic Videos: 0
```

Poster 정책:

- 실제 `cover_url`이 있는 작품만 local poster 생성
- coverless에 fake poster 생성 금지
- source image format 유지
- 불필요한 transcode 금지

NFO 정책:

- actual metadata only
- 없는 maker/people/genre를 지어내지 않음
- sparse metadata 허용

Jellyfin 정책:

- media mount read-only
- official/native API/scan 사용
- internal DB 직접 write 금지
- 기존 UserData/playback state 보존

Stage8은 `CLOSED / PASS`로 최종 freeze됐다.

---

# 6. Stage 9 — Completion + Organizer + Media Pipeline Production Automation — CLOSED / PASS

## 6.1 왜 새 Stage9가 필요했는가

기존 Downloader는 MP4가 완성되면 NAS `video2/downloads`까지 안전하게 publish했다.

그 뒤의:

```text
downloads
 -> JAV organizer
 -> holding commit
 -> NFO/poster
 -> Jellyfin
```

를 지속적으로 자동 처리하는 Production host-side chain이 필요했다.

Historical handoff의 `Stage9 Download button`은 이미 이전 단계에서 완료되었으므로 이번 Stage9는 **새로 정의된 completion/media automation stage**다.

## 6.2 개발 branch / commits

```text
worktree:
  /opt/missav-pwa-completion-stage9

branch:
  teddy-completion-stage9

97a35cbb539e5d1dd7ed1f43514cf3634691538c
  Add Stage9 completion and media pipeline

7dbad5aea8c8fb6f5906c1fa136852a1254c93dd
  Use separate Stage9 media state database
```

두 commit 모두 GitHub branch에 push 완료.

## 6.3 Stage9 핵심 모듈

```text
teddy_discovery_completion.py
teddy_discovery_completion_ssh.py
teddy_discovery_completion_apply.py
teddy_discovery_completion_orchestrator.py
teddy_discovery_completion_runner.py

teddy_discovery_media_metadata.py
teddy_discovery_media_publish.py
teddy_discovery_media_pipeline.py
teddy_discovery_jellyfin.py
teddy_discovery_media_jobs.py
```

각 영역의 smoke/recovery smoke도 함께 존재한다.

## 6.4 NAS transport

Stage9는 NAS에 SSH/SFTP 성격의 사용자 공간 transport를 사용한다.

```text
host: 192.168.1.201
user: ssikgun
downloads root: /volume1/video/video2/downloads
library root: /volume1/video/video2/JAV
```

list는 NAS 전체 recursive scan이 아니라 bounded shallow listing을 사용한다.

## 6.5 Completion / Organizer safety

흐름:

```text
NAS downloads candidate
 -> safe DVD-ID parse
 -> metadata/holding/collision check
 -> hidden partial publish
 -> size/state verification
 -> final publish
 -> Discovery holding commit
 -> source cleanup
```

복구 가능한 intermediate state와 collision fail-closed를 구현했다.

## 6.6 Metadata / poster / Jellyfin

Organizer 완료 후:

```text
JAV/PREFIX/DVD-ID/
  DVD-ID.mp4
  DVD-ID.nfo
  poster.<source-format>
```

을 생성한다.

Metadata는 Discovery DB의 actual title/release/maker/genres/people/cover를 사용한다.

Poster는 validated cover URL만 fetch한다.

Jellyfin은 official API로 새 media path를 notify한다.

## 6.7 Main Discovery DB를 v7로 올리지 않은 이유

초기 Stage9 source에서는 media retry state를 main Discovery DB의 `media_jobs` table로 추가하여 schema v7을 검토했다.

Production forensic 결과 기존 Discovery worker는 `SCHEMA_VERSION=6`보다 높은 DB를 거부하는 guard가 있음을 확인했다.

따라서 main Production DB를 v7로 올리는 계획을 중단하고:

```text
Discovery DB:
  teddy-discovery.sqlite3
  schema v6 유지

Stage9 Media retry DB:
  teddy-stage9-media.sqlite3
```

로 분리했다.

이 구조는 기존 Discovery R2와 Stage9 lifecycle을 안전하게 분리한다.

## 6.8 Production 설치

Frozen runtime:

```text
/opt/missav-dlp-web/stage9-runtime
```

runtime provenance marker:

```text
/opt/missav-dlp-web/stage9-runtime/.teddy-stage9-commit
= 7dbad5aea8c8fb6f5906c1fa136852a1254c93dd
```

Separate Media DB:

```text
/opt/missav-dlp-web/discovery/teddy-stage9-media.sqlite3
```

Media lock:

```text
/run/lock/teddy-stage9-media-writer.lock
```

Wrapper:

```text
/usr/local/sbin/teddy-completion-stage9-runner
```

Systemd:

```text
teddy-completion-stage9.service
teddy-completion-stage9.timer
```

Timer:

- enabled
- active
- 약 1분 간격
- 한 번에 completion 1건 + media retry 1건

Jellyfin secret:

```text
/opt/missav-dlp-web/teddy-jellyfin/jellyfin_api_key
```

NAS SSH secret:

```text
/opt/missav-dlp-web/teddy-nas-transfer/id_ed25519
/opt/missav-dlp-web/teddy-nas-transfer/known_hosts
```

secret value는 Git/log/handoff에 기록하지 않는다.

## 6.9 Stage9 real Production E2E — SIRO-5731

실제 신규 다운로드 1건으로 timer-driven E2E를 확인했다.

```text
DVD-ID: SIRO-5731
organizer job: 143 / COMPLETED
holding: 143 / present=1
canonical video:
  SIRO/SIRO-5731/SIRO-5731.mp4
media job: COMPLETED
attempt_count: 1
error: none
```

Sidecar:

```text
SIRO-5731.nfo: CREATED
poster: CREATED
```

Jellyfin notify:

```text
/media/adult/SIRO/SIRO-5731/SIRO-5731.mp4
JELLYFIN_NOTIFIED
```

Runner RC=0.

따라서 실전 자동 흐름:

```text
Downloader MP4 완성
 -> NAS downloads
 -> Stage9 자동 감지
 -> JAV canonical organize
 -> holdings update
 -> NFO/poster
 -> Jellyfin notify
```

가 Production에서 처음부터 끝까지 검증되었다.

**Stage9 = CLOSED / PASS**

---

# 7. 현재 반드시 보존할 invariant

1. Discovery DB는 현재 **schema v6**.
2. Stage9 retry state는 별도 `teddy-stage9-media.sqlite3`.
3. Jellyfin internal DB 직접 write 금지.
4. Jellyfin media mount read-only 유지.
5. coverless title에 fake poster 생성 금지.
6. actual metadata only / sparse metadata 허용.
7. Stage9 source cleanup은 destination + DB 검증 뒤에만.
8. same DVD-ID / destination collision은 fail closed.
9. 기존 Downloader startup/download가 Discovery/Stage9 실패 때문에 막히면 안 됨.
10. secret/API key/password를 Git/image/log에 넣지 않음.
11. NAS broad recursive scan 금지. bounded scan 또는 DB-known path 사용.
12. frozen/tested artifact identity를 이유 없이 rebuild하지 않음.
13. 기존 recovery/rollback artifact는 승인 없이 삭제하지 않음.

---

# 8. Stage9 이후 남은 작업 조사 결과

아래를 `확정적으로 남음`, `확인필요`, `재현 시만`으로 나눈다.

## 8.1 확정적으로 남은 것

### A. 보유 작품 기반 다운로드 사전 차단

현재 Discovery UI는 이미 holdings를 읽어 `보유 / 미보유`를 표시한다.

하지만 `/api/discovery/download`는 현재:

- availability/source resolve
- active queue duplicate guard

까지만 하고, **DB에 이미 보유 중인 DVD-ID인지 enqueue 전에 차단하지 않는다.**

따라서 보유 중인 작품도 다운로드 queue에 들어갈 수 있고, Stage9가 나중에 collision/holding으로 막는 구조가 될 수 있다. 네트워크/시간 낭비이므로 사전 차단이 필요하다.

### B. JAV filesystem ↔ holdings 주기적 reconciliation

초기 frozen 설계부터:

- existing JAV inventory를 holdings에 포함
- 신규 Stage9 완료 시 holdings 자동 추가
- 수동 NAS/File Station/SMB 변경을 주기적으로 reconciliation

하는 방향이었다.

현재 Stage9 신규 완료는 holdings를 갱신하지만, **현재 Production에 별도의 정기 JAV holdings reconciliation timer가 있는지는 아직 최신 live state에서 확인하지 않았다.**

다음 Stage 첫 forensic에서 확인 후 없으면 bounded reconciliation을 구현한다.

### C. Stage9 장애 알림/운영 가시성

현재 실패는 journald와 `teddy-stage9-media.sqlite3`에 남아 재시도된다.

그러나 `FAILED`가 장기간 쌓이거나 systemd service가 반복 실패할 때 사용자에게 알려주는 별도 alert는 없다.

### D. `.dockerignore`

과거 handoff에서 별도 hardening으로 남겨뒀고, 현재 Stage9 Git tree에도 `.dockerignore`가 없다.

Docker build context에서 `.git`, cache, logs, local transient/test artifact, local secret가 섞이지 않게 hardening할 가치가 있다.

### E. 123AV stream URL SSRF hardening

현재 `teddy_123av.py`의 resolved stream URL 검증은 핵심적으로:

- `https`
- hostname 존재

까지다.

과거 deferred 항목대로 loopback/private/link-local/local hostname/internal target 차단을 추가 검토한다.

## 8.2 확인필요

### Storage EXDEV edge case

예전 Downloader split-storage handoff에는 `os.replace() -> EXDEV` fallback hardening이 남아 있었다.

Stage9 자체 publish는 SSH remote에서 verified partial publish를 사용하므로 이 문제와 직접 같지 않다.

기존 Downloader publish path에 아직 실제 gap이 남았는지는 source/live forensic 후 판정한다. 증거 없이 재구현하지 않는다.

### Selkies 과거 TODO

오래된 handoff에는 persistent Chrome profile, final compose/network, UX cleanup 등이 남아 있었다.

그 후 Selkies 관련 source/runtime 작업이 많이 진행되었으므로 이 항목들은 stale 가능성이 높다. 새 Stage에서 필요할 때 최신 live state를 확인한 뒤 아직 남은 것만 재오픈한다.

## 8.3 재현 시만

### iPhone Safari 완료파일 `받기`

과거 한 차례 100% 후 `!` 사례가 있었지만 지속 재현되지 않았다.

다시 재현될 때만 Range/final-save/client-side 원인을 분리한다.

---

# 9. Future Feature 1 — 보유작 DB 정합성 + 중복 다운로드 방지

**판정: 가능 / 구현 난이도 낮음~중간 / 우선순위 높음**

새 DB를 또 만드는 것보다 현재 Discovery DB의 `holdings`를 그대로 ownership source로 쓰는 것이 가장 단순하고 안전하다.

이미 존재하는 것:

- `holdings` table
- initial JAV inventory
- Stage7/Stage9 holding commit
- UI data의 `owned`, `holding_count`
- frontend `보유 / 미보유` badge

따라서 핵심은 새 DB 구축이 아니라 **holdings를 실제 JAV와 계속 맞추고, 다운로드 front-door에서 활용하는 것**이다.

## 권장 구조

### Step A — ownership canonical rule

```text
보유 = holdings에
       dvd_id 일치
       parse_status=MATCHED
       present=1
       row가 1개 이상
```

DB row를 과거 이력까지 무조건 삭제하기보다 `present=0`으로 history를 남기는 쪽을 선호한다.

### Step B — Discovery 다운로드 사전 guard

`POST /api/discovery/download`에서 source resolve/enqueue 전에 holdings를 read-only check한다.

보유 중이면:

```text
HTTP 409
status: owned
message: 이미 보유 중인 작품입니다
```

로 queue에 넣지 않는다.

active queue duplicate와 library owned는 서로 다른 이유이므로 상태를 분리한다.

### Step C — UI

현재 `보유 / 미보유`는 이미 동작한다.

추가 개선:

```text
보유 작품       -> 다운로드 버튼 disabled / "보유 중"
미보유 + source -> 다운로드
다운로드 중     -> "다운로드 중"
완료/정리 대기  -> "정리 대기"
```

### Step D — 직접 URL 입력도 막을지 결정

Discovery 버튼만 막으면 최소 변경이다.

하지만 Teddy의 최종 요구가 **Downloader 전체에서 같은 DVD-ID 재다운로드를 막기**라면 일반 `/download` front-door에서도 URL에서 authoritative DVD-ID가 안전하게 추출되는 경우에 holdings guard를 추가할 수 있다.

권장 rollout:

1. Discovery button guard canary
2. false-positive 0 확인
3. 그 뒤 generic/manual URL front-door까지 확대 여부 결정

모든 generic URL을 억지로 DVD-ID로 해석하면 안 된다.

### Step E — bounded holdings reconciliation

주 1회 정도:

```text
DB-known canonical path
 + JAV의 PREFIX/DVD-ID/DVD-ID.ext 구조
```

만 좁게 확인한다.

NAS 전체 recursive scan 금지.

목표:

- DB present=1인데 파일 없음 -> present=0
- canonical media가 있는데 DB missing -> 안전하게 holding 추가
- ambiguity/collision -> 자동 수정하지 않고 HOLD/report

## Acceptance canary

최소:

1. 이미 보유 중 DVD-ID 1개 -> download enqueue 0
2. 미보유 DVD-ID 1개 -> 정상 enqueue
3. UI owned/unowned 정확
4. 새 다운로드 완료 후 Stage9가 holding 추가
5. reconciliation에서 삭제/수동 변경 1건을 안전하게 반영

---

# 10. Future Feature 2 — 보유 작품 한국어 자막 다운로드 / 생성

**판정: 가능 / 구현 난이도 중간~높음 / 단계적 canary 권장**

가장 스마트한 방법은 `자막이 이미 있으면 재사용`, `없을 때만 AI 생성`하는 우선순위 체인이다.

## 10.1 권장 우선순위

### Priority 1 — 기존 subtitle track / sidecar 사용

먼저 media 자체에 subtitle stream이 있는지 `ffprobe`로 확인한다.

이미 한국어 자막이 있으면 아무 것도 생성하지 않는다.

일본어/영어 subtitle track이 있으면 sidecar로 extract 후 번역 후보로 사용한다.

일부 extractor/HLS source가 subtitle track 정보를 제공할 수도 있으므로 upstream에 실제 text subtitle이 있으면 Whisper보다 우선한다.

### Priority 2 — 신뢰 가능한 외부 subtitle source

DVD-ID exact match가 가능한 합법적/신뢰 가능한 provider가 실제로 있는지 별도 forensic한다.

있다면:

```text
exact DVD-ID match
 -> download
 -> encoding/timestamp/content validation
 -> Korean 여부 확인
 -> safe sidecar publish
```

로 끝내는 것이 가장 저렴하다.

JAV는 일반 영화/TV subtitle ecosystem보다 provider coverage가 불안정할 가능성이 높으므로, 특정 사이트를 설계에 고정하지 않고 실제 hit-rate를 먼저 측정한다.

### Priority 3 — AI subtitle 생성

외부/embedded subtitle이 없으면:

```text
video audio
 -> Japanese ASR
 -> timestamped Japanese transcript
 -> Korean translation
 -> timestamp-preserved Korean SRT
 -> JAV sidecar publish
 -> Jellyfin refresh/notify
```

을 사용한다.

## 10.2 ASR 엔진 권장

`faster-whisper`를 1순위 후보로 권장한다.

이유:

- Whisper multilingual Japanese ASR 사용 가능
- CTranslate2 기반으로 GPU memory/속도 효율이 좋음
- int8 등으로 VRAM 사용량을 낮출 수 있음
- Subgen 같은 기존 프로젝트도 `stable-ts + faster-whisper` 조합으로 Jellyfin/Plex/Emby subtitle 생성을 하고 있어 검증된 방향성이 있음

Whisper 자체 `translate` task는 non-English speech를 **English로 번역**하는 기능이다. Japanese -> Korean을 바로 맡기는 경로로 쓰지 않는다.

따라서:

1. Whisper/faster-whisper = 일본어 음성 -> 일본어 transcript + timestamp
2. 별도 translation model = 일본어 text -> 한국어 text

로 역할을 분리한다.

## 10.3 번역 단계

SRT timing은 고정하고 text만 번역한다.

```text
index
start --> end
Japanese text
```

에서 index/timestamp를 절대 바꾸지 않고 text block만 한국어로 변환한다.

LLM 번역은 여러 cue를 bounded batch로 묶되:

- cue 개수 보존
- timestamp 수정 금지
- 누락/합치기 금지
- 원문과 번역 line mapping 검증

을 deterministic validator로 강제한다.

## 10.4 Jellyfin/Infuse sidecar

Jellyfin 공식 naming 방식에 맞춰 video basename을 공유한다.

예:

```text
SIRO-5731.mp4
SIRO-5731.ko.srt
```

필요 시 default flag를 별도 정책으로 정할 수 있지만 처음에는 `DVD-ID.ko.srt`가 단순하다.

영상 자체를 다시 encode해서 자막을 burn-in하지 않는다.

장점:

- 원본 video byte 불변
- 실패 시 SRT만 교체 가능
- Jellyfin/Infuse에서 언어 track 선택 가능
- 재생/다운로드 pipeline과 분리

## 10.5 실행 위치

Whisper/translation 같은 무거운 처리를 CT108 Downloader나 CT112 Jellyfin process 안에 직접 넣지 않는 것을 권장한다.

별도 GPU worker가:

- NAS/JAV media를 read-only 입력으로 읽고
- 임시 working directory에서 ASR/번역
- 검증된 `.ko.srt`만 Stage9와 같은 safe publish boundary를 통해 NAS에 작성

하도록 분리한다.

## 10.6 durable subtitle state

main Discovery DB v6를 다시 건드리지 않고 별도 state DB를 두는 방향이 안전하다.

예:

```text
teddy-subtitle-jobs.sqlite3

subtitle_jobs:
  dvd_id
  status
  method
  source_language
  source_kind
  model/version
  output_sha256
  attempt_count
  error
  updated_at
```

상태:

```text
PENDING
RUNNING
COMPLETED
FAILED
SKIPPED_EXISTING
```

Stage9 media retry와 같은 방식으로 crash/retry를 durable하게 만든다.

## 10.7 첫 canary 권장

처음부터 전체 JAV library에 돌리지 않는다.

1개 작품만 선택하여:

1. embedded/external subtitle inventory
2. audio language 확인
3. faster-whisper Japanese transcription
4. Korean translation
5. timing/encoding validator
6. `DVD-ID.ko.srt` safe publish
7. Jellyfin readback
8. 실제 재생 품질 확인

후 속도/정확도/VRAM/번역 품질을 보고 5개 정도로 확대한다.

---

# 11. 추천 Next Roadmap

## Stage 10 — Holdings Integrity + Duplicate Download Prevention

목표:

```text
실제 JAV library
 <-> holdings DB
 <-> Discovery/UI/download front-door
```

을 일관되게 만든다.

우선순위:

1. 최신 live holdings reconciliation forensic
2. periodic reconciliation 존재 여부 확인
3. owned pre-enqueue guard
4. UI `보유 중` download state
5. direct URL front-door까지 확대 여부 결정
6. bounded weekly reconciliation
7. real owned/unowned canary

이 Stage는 현재 구조를 거의 그대로 재사용하므로 가장 먼저 하는 것이 좋다.

## Stage 11 — Korean Subtitle Pipeline

목표:

```text
existing subtitle
 -> trusted download
 -> ASR + Korean translation
```

순으로 한국어 SRT를 확보한다.

원칙:

- 원본 MP4 불변
- external `.ko.srt`
- 별도 GPU worker
- separate durable job DB
- 1개 real canary부터
- Jellyfin official refresh/notify

## Stage 12 — Operations / Hardening

확정/검증 대상:

- Stage9/Subtitle `FAILED` alert
- Stage9 separate DB backup/readback 정책 확인
- `.dockerignore`
- 123AV SSRF hardening
- EXDEV old gap 실제 잔존 여부 forensic
- stale Selkies TODO reconciliation
- Safari 문제는 재현 시만

기능 Stage10/11과 security hardening을 한 commit에 섞지 않는다.

---

# 12. Subtitle 연구 참고

다음 upstream 문서를 기준으로 설계한다.

- Jellyfin Movies / External Subtitles:
  `https://jellyfin.org/docs/general/server/media/movies/`
- OpenAI Whisper:
  `https://github.com/openai/whisper`
- faster-whisper:
  `https://github.com/SYSTRAN/faster-whisper`
- Subgen:
  `https://github.com/McCloudS/subgen`

핵심 확인사항:

- Jellyfin은 video basename + language suffix external subtitle을 지원한다.
- Whisper는 multilingual speech recognition을 지원한다.
- Whisper translate task의 target은 English이므로 Korean 번역은 별도 단계가 필요하다.
- faster-whisper는 GPU/CTranslate2 기반 효율적 ASR 후보다.
- Subgen은 Jellyfin webhook + local subtitle generation의 참고 구현으로 활용 가능하지만 Korean translation은 별도 설계한다.

---

# 13. 다음 대화방 시작용 요약

```text
Stage0~9은 CLOSED/PASS다.
Stage9 Production timer는 exact commit 7dbad5a 기반으로 동작 중이고,
SIRO-5731 실제 신규 다운로드 E2E까지 성공했다.

다음 우선 작업은 Stage10:
JAV holdings 정합성 + 이미 보유한 작품의 사전 다운로드 차단이다.
현재 UI/backend data에는 owned/holding_count가 이미 있으므로 새 library DB를 만들지 말고
기존 holdings를 canonical ownership으로 사용한다.

그 다음 Stage11:
한국어 subtitle 확보 파이프라인을 1개 canary로 설계한다.
existing/embedded -> trusted download -> faster-whisper Japanese ASR -> Korean translation -> DVD-ID.ko.srt 순서가 기본이다.

작업은 항상 live read-only forensic -> source-only -> smoke -> canary -> 승인된 Production apply 순서로 진행한다.
```

---

# 14. 최종 판정

```text
DISCOVERY_STAGE0_8=CLOSED/PASS
STAGE9_COMPLETION_MEDIA=CLOSED/PASS
STAGE9_PRODUCTION_TIMER=ACTIVE/ENABLED
STAGE9_REAL_E2E_SIRO_5731=PASS
DISCOVERY_DB_SCHEMA=6
MAIN_DB_MEDIA_JOBS=NONE
SEPARATE_STAGE9_MEDIA_DB=ACTIVE
NEXT_STAGE10=HOLDINGS_INTEGRITY_AND_DUPLICATE_GUARD
NEXT_STAGE11=KOREAN_SUBTITLE_PIPELINE
```
