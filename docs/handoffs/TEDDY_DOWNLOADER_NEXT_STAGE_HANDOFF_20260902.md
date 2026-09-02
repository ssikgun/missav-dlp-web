# Teddy Downloader — Next Stage Frozen Handoff

- 작성일: 2026-09-02 KST
- 프로젝트: Downloader / Teddy Discovery
- Repository: `ssikgun/missav-dlp-web`
- 기준 브랜치: `teddy-completion-stage9`
- Stage0~9 최종 이력 정본:
  `docs/handoffs/TEDDY_DOWNLOADER_DISCOVERY_STAGE9_FINAL_HANDOFF_20260902.md`
- 상태: **Stage0~9 CLOSED / PASS**
- 이 문서의 역할: **Stage10 이후 해야 할 일을 고정하는 최신 Next-Stage Handoff**

---

# 1. 현재 기준점

현재 Production에서 다음 흐름은 실전 검증까지 완료되었다.

```text
Discovery
 -> 다운로드 요청
 -> 기존 Teddy Downloader
 -> MP4 완성
 -> NAS /video2/downloads
 -> Stage9 자동 감지
 -> JAV canonical 정리
 -> holdings 등록
 -> NFO / poster 생성
 -> Jellyfin notify/index
```

Stage9 실전 신규 작품 `SIRO-5731`로 timer-driven E2E가 PASS했다.

현재 중요한 기준:

```text
Discovery DB schema: v6
Stage9 media retry DB: separate DB
Stage9 timer: enabled / active
Stage9 runtime commit: 7dbad5aea8c8fb6f5906c1fa136852a1254c93dd
```

Stage0~9의 완료 기능을 이유 없이 재설계하거나 재구현하지 않는다.

---

# 2. Teddy와 작업할 때 지켜야 할 방식

## checkpoint 보고

Teddy가 terminal/checkpoint 결과를 붙이면 첫 visible token은 반드시:

```text
PASS
FAIL
INCOMPLETE
```

중 하나다.

긴 로그를 그대로 반복하지 않고, 쉬운 한국어로 핵심만 설명한다.

가능하면 끝에:

```text
지금 한 일:
다음 할 일:
```

을 짧게 남긴다.

## 명령 위치

모든 명령 블록에는 실행 위치를 명시한다.

예:

```text
PVE Host — root@pve
CT108 Downloader LXC — root@downloader
CT112 Media/Jellyfin LXC
VM122 Local-LLM VM
```

명령어는 대상과 shell 문법을 다시 확인한 뒤 제공한다.

## 변경/삭제 안전

삭제, purge, destroy, unmount, config 제거, 서비스 중단/재부팅, Production DB/NAS/Jellyfin write, repository 변경 등 실제 상태를 바꾸는 작업은 무엇을 바꿀지 정확히 설명하고 Teddy의 승인 범위 안에서만 수행한다.

기존 rollback/recovery artifact를 별도 승인 없이 삭제하지 않는다.

## NAS scan 안전

NAS 전체를 broad recursive `find`, `rglob`, `du` 등으로 훑지 않는다.

현재 canonical layout과 DB-known path를 활용한 bounded 검사를 사용한다.

---

# 3. FROZEN NEXT ROADMAP

다음 Stage 순서를 현재 기준으로 고정한다.

```text
Stage10
  Holdings Integrity + Duplicate Download Prevention

Stage11
  Korean Subtitle Acquisition / Generation Pipeline

Stage12
  Operations / Hardening
```

새로운 요구가 생기더라도 이 순서를 무심코 재정의하지 않는다.

변경이 필요하면 먼저 Teddy와 이유를 확인한다.

---

# 4. Stage10 — Holdings Integrity + Duplicate Download Prevention

## 목표

> 실제 JAV 보유 상태와 Discovery DB를 일치시키고, 이미 보유한 작품은 어떤 지원되는 다운로드 진입 경로를 사용하더라도 다운로드 시작 전에 차단한다.

새 보유작 DB를 추가로 만들지 않는다.

현재 Discovery DB의 `holdings`를 canonical ownership source로 사용한다.

이미 현재 코드에는:

```text
holdings table
owned
holding_count
보유 / 미보유 UI badge
Stage9 신규 completion 시 holding commit
```

이 존재한다.

즉 Stage10의 핵심은 새 DB 구축이 아니라:

```text
JAV filesystem
 <-> holdings
 <-> UI
 <-> 모든 주요 enqueue front-door
```

를 하나로 연결하는 것이다.

---

# 5. Stage10-A — JAV ↔ holdings 정합성

## canonical ownership rule

기본 보유 판정:

```text
holdings.dvd_id = 대상 DVD-ID
parse_status = MATCHED
present = 1
row count >= 1
```

과거 이력을 무조건 DELETE하기보다 실제 파일이 사라진 경우 `present=0` 형태로 보존하는 쪽을 우선 검토한다.

## 자동 반영해야 할 상황

### Stage9 신규 작품

이미 동작 중이다.

```text
다운로드 완료
 -> Stage9 organizer
 -> JAV
 -> holding 등록
```

이 경계를 유지한다.

### NAS에 수동 추가

File Station / SMB 등으로 사람이 JAV에 직접 media를 추가한 경우 안전하게 DVD-ID를 판정하여 holdings에 반영한다.

### NAS에서 수동 삭제

실제 canonical media가 사라졌다면 reconciliation 후 해당 holding을 `present=0`으로 반영한다.

### DB ↔ filesystem contradiction

```text
DB present=1 + 실제 파일 없음
실제 canonical media 존재 + holding 없음
```

을 찾아 안전하게 reconciliation한다.

ambiguity / duplicate / unexpected layout은 자동 추측하지 않고 HOLD/report한다.

## scan 정책

NAS 전체 무제한 recursive scan 금지.

현재 구조:

```text
JAV/PREFIX/DVD-ID/DVD-ID.ext
```

를 활용한다.

권장:

```text
DB-known canonical paths
+
JAV root -> PREFIX -> DVD-ID 정도의 bounded depth
```

주기적 reconciliation은 우선 주 1회 수준으로 검토한다.

정확한 schedule은 live forensic 후 결정한다.

---

# 6. Stage10-B — 공통 Ownership Guard

## 핵심 원칙

버튼마다 제각각 중복 검사를 구현하지 않는다.

가능하면 실제 enqueue 직전의 공통 경계에서:

```text
URL / DVD-ID
 -> authoritative DVD-ID resolve
 -> holdings ownership check
 -> active queue duplicate check
 -> enqueue
```

순으로 처리한다.

`이미 보유 중`과 `이미 다운로드 큐에 있음`은 서로 다른 상태로 구분한다.

보유 중이면 다운로드를 시작하지 않는다.

예상 응답 의미:

```text
status: owned
HTTP 409
message: 이미 보유 중인 작품입니다.
```

구체적인 API shape은 기존 계약을 먼저 읽은 뒤 최소 변경으로 결정한다.

---

# 7. Stage10-C — 반드시 검사해야 하는 다운로드 진입 경로

## 1) Discovery 다운로드 버튼

Discovery의:

```text
최신
주간
월간
장르
```

등 모든 카드의 다운로드 버튼.

보유작이면:

```text
보유 중
```

으로 표시하고 enqueue하지 않는다.

현재 UI에 이미 `보유 / 미보유` 정보가 있으므로 해당 backend state와 실제 다운로드 동작을 연결한다.

---

## 2) Browser 탭의 다운로드 버튼 — 필수

Teddy가 직접 추가한 확정 요구사항이다.

Downloader의 Browser 탭에서 VPN Browser로 작품 페이지를 보고 **Browser 옆의 다운로드 버튼을 눌러 Downloader queue에 추가하는 경로도 반드시 보유 중복 검사를 거쳐야 한다.**

목표 흐름:

```text
Browser 탭
 -> Browser 다운로드 버튼
 -> 대상 URL
 -> authoritative DVD-ID resolve
 -> holdings check
 -> 보유 중이면 enqueue 차단
 -> 미보유면 기존 enqueue
```

이 경로를 Discovery 전용 코드에 복붙하지 않는다.

가능하면 공통 Ownership Guard를 재사용한다.

Stage10 첫 read-only forensic에서 Browser 버튼이 실제로 어느 JS/API/backend enqueue 경계를 타는지 먼저 확인한다.

---

## 3) 일반 Downloader URL 입력

최종적으로 지원 가능한 사이트에 한해서 ownership guard를 적용한다.

예:

```text
MissAV
123AV
기타 authoritative parser가 안전하게 DVD-ID를 식별할 수 있는 source
```

모든 URL에서 무리하게 DVD-ID를 추출하지 않는다.

DVD-ID를 확실히 판별할 수 없는 generic URL은 기존 Downloader 동작을 보존한다.

권장 rollout:

```text
Discovery guard
 -> Browser button guard
 -> canary / false positive 0 확인
 -> 일반 URL front-door 확대
```

---

# 8. Stage10-D — UI 상태 개선

현재 UI에는 이미:

```text
보유
미보유
```

badge가 있다.

Stage10에서는 이것을 실제 다운로드 정책과 연결한다.

예:

```text
보유 작품
  보유 중
  Download button disabled

미보유 + source 있음
  다운로드
```

핵심 기능이 안정화된 뒤 필요하면 다음 상태까지 확장할 수 있다.

```text
다운로드 중
NAS downloads 도착
정리 대기
보유 완료
```

이 추가 상태 표시는 Stage10 core acceptance를 늦추지 않는 범위에서만 한다.

---

# 9. Stage10 Acceptance Criteria

실제 canary에서 최소 다음을 확인한다.

1. 이미 보유한 DVD-ID를 Discovery 다운로드 버튼에서 요청 -> enqueue 0.
2. 같은 보유작을 Browser 탭 다운로드 버튼에서 요청 -> enqueue 0.
3. 같은 보유작을 지원되는 일반 URL 입력으로 요청 -> enqueue 0.
4. active queue duplicate와 owned 상태가 구분되어 보고됨.
5. 미보유 작품 -> 정상 enqueue.
6. 다운로드 완료 -> Stage9가 JAV로 정리하고 holding 자동 등록.
7. 방금 완료한 같은 DVD-ID를 다시 요청 -> 사전 차단.
8. NAS에서 수동 삭제한 작품 -> reconciliation 후 미보유.
9. NAS에 수동 추가한 작품 -> reconciliation 후 보유.
10. ambiguity / unsafe path / duplicate physical media는 자동 추측하지 않고 HOLD/report.
11. 기존 Downloader의 지원 불가능 generic URL 동작에 회귀 없음.

전부 통과하면:

```text
Stage10 = CLOSED / PASS
```

---

# 10. Stage11 — Korean Subtitle Acquisition / Generation Pipeline

## 목표

> 보유한 작품에 한국어 자막이 없을 때 가장 비용이 적고 정확한 방법부터 순서대로 찾아서, 필요할 때만 AI로 한국어 SRT를 생성한다.

영상 자체를 재인코딩하거나 burn-in하지 않는다.

권장 결과:

```text
DVD-ID.mp4
DVD-ID.nfo
poster.jpg
DVD-ID.ko.srt
```

원본 MP4 byte는 불변으로 유지한다.

---

# 11. Stage11-A — 자막 확보 우선순위

## Priority 1 — 이미 존재하는 자막

먼저 확인:

```text
embedded subtitle track
existing sidecar
```

한국어 자막이 이미 있으면 `SKIPPED_EXISTING`으로 종료한다.

일본어/영어 등 텍스트 subtitle이 있으면 Whisper를 쓰지 않고 번역 source로 활용한다.

텍스트 자막이 있는데 음성 ASR부터 다시 하는 낭비를 피한다.

---

## Priority 2 — 외부 자막 source

DVD-ID exact match가 가능한 신뢰할 수 있는 외부 subtitle source를 조사한다.

처음부터 특정 provider를 시스템에 고정하지 않는다.

먼저 약 20~30개 품번으로:

```text
한국어 exact-match hit rate
일본어 subtitle hit rate
잘못 매칭되는 비율
encoding/timestamp 품질
```

을 조사한다.

실제로 유용한 source가 확인된 경우에만 provider adapter를 설계한다.

---

## Priority 3 — AI 자막 제작

기존/외부 자막이 없을 때만 AI를 사용한다.

권장 pipeline:

```text
일본어 음성
 -> Japanese ASR
 -> timestamped Japanese transcript
 -> Japanese -> Korean text translation
 -> timestamp-preserved Korean SRT
 -> validation
 -> safe publish
 -> Jellyfin refresh/notify
```

Whisper 계열은 일본어 음성 인식 담당.

한국어 번역은 별도 translation 단계가 담당한다.

Whisper의 translate task를 일본어 -> 한국어 번역기로 오해하지 않는다.

---

# 12. Stage11-B — Subtitle Worker 위치: VM122 Local-LLM VM 우선 후보

Teddy가 지정한 우선 후보는 **VM122 Local-LLM VM**이다.

현재 알고 있는 환경:

```text
VM122
Local-LLM 용도
RTX 3060 12GB GPU 포함
```

또한 기존 YouTube 지식 저장/요약 workflow 쪽에서 `faster-whisper` 기반 STT 준비 또는 사용 이력이 있는 것으로 파악된다.

기존 자료에서는 다음 workflow가 확인된 적이 있다.

```text
yt-dlp audio
 -> ffmpeg 16k mono
 -> faster-whisper
 -> timestamped transcript
 -> local LLM processing
```

그러나 **Stage11 구현 전에 VM122의 실제 live state를 반드시 read-only로 확인한다.**

확인 없이 "이미 GPU faster-whisper가 완성돼 있다"고 가정하지 않는다.

## VM122 Stage11 사전 확인 항목

Stage11 CP1/CP2에서 최소 다음을 확인한다.

```text
VM ID / hostname / OS
RTX 3060 12GB passthrough 및 nvidia-smi
CUDA / NVIDIA runtime 상태
현재 llama.cpp / local-LLM 서비스와 VRAM 사용량
faster-whisper 설치 위치
faster-whisper 버전
Python venv 위치
CTranslate2 / CUDA GPU inference 가능 여부
ffmpeg / ffprobe
현재 YouTube STT script/venv가 VM122에 실제 존재하는지
기존 STT model / compute_type
GPU 동시사용/locking 정책
ASR 작업 중 local LLM service 영향
NAS media read 경계
임시 working directory / disk 여유
```

## VM122 채택 기준

다음이 만족되면 VM122를 Subtitle Worker로 우선 사용한다.

```text
GPU inference 정상
기존 local LLM 운영에 위험한 간섭 없음
필요한 ffmpeg/faster-whisper stack 재사용 가능
NAS read 또는 안전한 input 전달 가능
작업 queue/lock으로 GPU 사용을 직렬화 가능
```

가능하면 기존 YouTube STT용 faster-whisper environment를 **무작정 복제하거나 재설치하지 않고**, 실제 구조를 읽은 뒤 재사용 가능한 부분만 활용한다.

반대로 GPU/서비스 충돌이 크다면 그 증거를 확인한 뒤 별도 worker 구조를 재검토한다.

VM122를 우선 후보로 고정하되, live forensic 이전에는 설치/서비스 변경을 하지 않는다.

---

# 13. Stage11-C — ASR / 번역 역할 분리

권장 ASR 후보:

```text
faster-whisper
```

이유:

- multilingual Japanese ASR
- CTranslate2 GPU 지원
- RTX 3060 12GB에서 현실적인 운용 가능성
- 기존 VM122 STT 자산 재사용 가능성

하지만 model size / compute type은 Stage11 live benchmark 후 결정한다.

기존 local LLM workload와 동시에 GPU를 과점유하지 않는다.

번역은 별도 단계다.

```text
ASR = 일본어 speech -> 일본어 text + timing
Translation = 일본어 text -> 한국어 text
```

SRT cue index와 timestamp는 번역 모델이 수정할 수 없게 deterministic validation을 둔다.

검증 항목:

```text
cue count 동일
start/end timestamp 동일
빈 번역 block 금지
cue merge/split 금지 또는 명시적 controlled policy
UTF-8 정상
SRT syntax 정상
```

---

# 14. Stage11-D — Subtitle state DB

main Discovery DB v6를 자막 작업 때문에 바로 확장하지 않는다.

Stage9 media job과 비슷하게 별도 state DB를 우선 검토한다.

예:

```text
teddy-subtitle-jobs.sqlite3
```

예상 logical state:

```text
PENDING
RUNNING
COMPLETED
FAILED
SKIPPED_EXISTING
```

예상 metadata:

```text
dvd_id
method
source_kind
source_language
asr_model/version
translation_model/version
output_path
output_sha256
attempt_count
error
created_at
updated_at
```

실패가 Downloader/Stage9/Jellyfin core를 막지 않도록 분리한다.

---

# 15. Stage11-E — safe publish / Jellyfin

자막은 영상 옆 external sidecar로 publish한다.

예:

```text
JAV/SIRO/SIRO-5731/SIRO-5731.mp4
JAV/SIRO/SIRO-5731/SIRO-5731.ko.srt
```

영상 파일 자체는 변경하지 않는다.

publish 전에:

```text
SRT syntax
encoding
non-empty
hash
canonical filename
existing target collision
```

을 검사한다.

기존 파일과 충돌하면 자동 overwrite하지 않는다.

검증된 sidecar 작성 후 Jellyfin의 official/native refresh 또는 notify 경계를 사용한다.

Jellyfin internal DB 직접 write 금지.

---

# 16. Stage11 First Canary

전체 보유작을 한 번에 처리하지 않는다.

첫 작품 1개만 선택한다.

순서:

```text
1. media/audio/subtitle inventory
2. embedded/existing subtitle 확인
3. 외부 exact subtitle source 조사
4. 필요할 때만 VM122 faster-whisper Japanese ASR
5. Korean translation
6. deterministic SRT validation
7. .ko.srt safe publish
8. Jellyfin readback
9. 실제 재생에서 자막 품질 확인
10. GPU/시간/VRAM 사용량 기록
```

통과하면:

```text
1 title
 -> 5 title batch
 -> small batch
 -> optional automation
```

순서로 확대한다.

---

# 17. Stage11 Acceptance Criteria

최소:

1. 기존 한국어 자막이 있으면 AI 미실행.
2. 기존 일본어/영어 텍스트 자막이 있으면 ASR 미실행.
3. 외부 exact subtitle source가 있으면 안전하게 활용 가능.
4. 자막이 없으면 VM122에서 Japanese ASR 수행 가능.
5. 한국어 번역 후 timing 유지.
6. `.ko.srt`가 UTF-8/SRT validator PASS.
7. MP4/NFO/poster byte 불변.
8. existing subtitle collision 시 overwrite 금지.
9. Jellyfin이 한국어 external subtitle을 인식.
10. 실패 시 subtitle job에 durable state가 남고 Stage9 core에는 영향 없음.
11. VM122 local LLM 기존 서비스에 허용 불가 수준의 GPU/메모리 영향 없음.

---

# 18. Stage12 — Operations / Hardening

Stage10/11의 기능 구현과 섞지 않고 별도 진행한다.

현재 후보:

```text
Stage9 FAILED 장기 누적 alert
Subtitle FAILED alert
Stage9 media DB backup/readback 정책
Subtitle DB backup 정책
.dockerignore 추가
123AV SSRF hardening
과거 EXDEV gap 실제 잔존 여부 forensic
stale Selkies TODO reconciliation
iPhone Safari 완료파일 문제는 재현 시만
```

## 123AV hardening

현재 stream URL validation을 최신 source에서 다시 확인한 뒤 필요하면:

```text
loopback
private IP
link-local
local/internal hostname
unexpected redirect target
```

등을 차단하는 outbound policy를 추가한다.

증거 없이 unrelated downloader network code를 넓게 재설계하지 않는다.

---

# 19. 다음 대화방에서 가장 먼저 할 일

바로 코딩하지 않는다.

## Stage10 CP1 — READ ONLY forensic

확인:

```text
Production holdings 현재 schema/data
JAV canonical layout
기존 periodic reconciliation code/timer 존재 여부
Discovery download enqueue 경계
Browser 탭 다운로드 버튼 JS/API/backend 경계
일반 URL input enqueue 경계
공통 Ownership Guard를 넣기 가장 작은 위치
현재 active queue duplicate guard와의 관계
```

그 다음:

```text
read-only forensic
 -> frozen design
 -> source-only change
 -> deterministic smoke
 -> canary
 -> Teddy 승인
 -> Production apply
```

순서로 진행한다.

Stage11 시작 시에도 동일하게 먼저 VM122를 read-only forensic한다.

---

# 20. 하지 말아야 할 것

```text
새 ownership DB를 이유 없이 추가
holdings 대신 Jellyfin DB를 보유 source로 사용
Jellyfin DB 직접 수정
NAS 전체 recursive scan
보유작인데 일단 다운로드 후 Stage9 collision에 맡기기
Browser 다운로드 버튼만 별도 duplicate 로직 복붙
모든 generic URL을 DVD-ID로 강제 해석
자막을 video에 burn-in
전체 JAV library에 Whisper 일괄 실행
VM122 live 확인 전에 faster-whisper/GPU package 재설치
local LLM GPU workload를 무시하고 ASR 병렬 실행
외부 subtitle provider를 hit-rate 검증 없이 고정
existing SRT 자동 overwrite
```

---

# 21. 최종 사용자 목표

최종적으로 Teddy Downloader는 다음처럼 동작해야 한다.

```text
이미 보유한 작품
 -> Discovery에서 눌러도 차단
 -> Browser 탭 다운로드 버튼에서 눌러도 차단
 -> 지원되는 일반 URL로 요청해도 차단

미보유 작품
 -> 정상 다운로드
 -> Stage9가 JAV로 자동 정리
 -> metadata/poster/Jellyfin 처리
 -> holdings에 보유 등록

보유 완료 작품
 -> 기존 한국어 자막 확인
 -> 외부 자막 확인
 -> 없으면 VM122 GPU Worker로 AI 자막 생성
 -> DVD-ID.ko.srt
 -> Jellyfin/Infuse에서 선택 재생
```

한 줄 목표:

> **이미 가진 작품은 어디서 다운로드를 눌러도 다시 받지 않고, 보유 작품에는 가능한 가장 효율적인 방법으로 한국어 자막까지 자동으로 붙여주는 Downloader.**

---

# 22. Frozen Status

```text
STAGE0_9=CLOSED/PASS
NEXT_STAGE10=HOLDINGS_INTEGRITY_AND_DUPLICATE_GUARD
STAGE10_DISCOVERY_GUARD=REQUIRED
STAGE10_BROWSER_BUTTON_GUARD=REQUIRED
STAGE10_SUPPORTED_URL_GUARD=REQUIRED
STAGE10_RECONCILIATION=REQUIRED

NEXT_STAGE11=KOREAN_SUBTITLE_PIPELINE
STAGE11_WORKER_PREFERRED=VM122_LOCAL_LLM
STAGE11_GPU=RTX3060_12GB
STAGE11_VM122_LIVE_FORENSIC_BEFORE_USE=REQUIRED
STAGE11_EXISTING_SUBTITLE_FIRST=REQUIRED
STAGE11_EXTERNAL_SUBTITLE_SECOND=REQUIRED
STAGE11_AI_ASR_LAST=REQUIRED
STAGE11_VIDEO_REENCODE=FORBIDDEN

NEXT_STAGE12=OPERATIONS_AND_HARDENING
```
