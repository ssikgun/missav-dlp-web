# Teddy Downloader — 살아 있는 작업 로드맵 (WORK_ROADMAP)

ROADMAP_VERSION: 2
UPDATED_AT: 2026-11-05 KST (Stage9 포스터 자동 폴백 INCOMPLETE / NFO 완료 증거 정리 / 파일관리 UI 후속 등록)
CANONICAL_REPO: ssikgun/missav-dlp-web
CANONICAL_BRANCH: teddy-subtitle-stage11
TRACKER_STATUS: ACTIVE — informational progress and priorities, NOT a task authorization


## 0. 최신 확인 결과 — 2026-11-05

- **P00 v1.0.7 후보:** 기존 포스터 경로 복원 및 격리된 페이지·JPEG 연결을 일부 검증했다. 실제 저장된 페이지 형식과 신규 작품 자동 실행 연결이 미완료이므로 제품 소스 미반영, 4건 운영 시험 NOT_RUN.

- **포스터 출처 정책 승인(12시 이후 사용자 승인):** 기존 메타데이터 `cover_url`을 Stage8에서 검증·채택해 온 소스 포스터로 계속 사용하고, 발행사 공식 인증용 신규 필드를 요구하지 않는다. 계약 **v1.0.7 승인**. 이미지 형식·URL·작품 일치 검증은 유지하고, 연결이 검증된 Fourhoi JPEG만 `cover.jpg`로 저장한다. 제품 코드는 아직 미승격; 네 작품 운영 시험은 NOT_RUN.

- **P00 후보 보완:** 격리 후보의 `/dmNN/ko/` 작품 검증과 관련 오프라인 회귀를 확인했으나 페이지 입력의 자동 연결과 기존 정식 포스터 경로 보존은 미완료. 실사이트·운영 시험은 NOT_RUN.

- **현재 보유 작품:** Discovery DB의 현재 JAV 보유 **260개**, 모두 제목 행·비어 있지 않은 제목·유효한 raw JSON 존재 **260/260 PASS (읽기 전용)**. 이는 메타데이터 필드 전체의 정확성이나 NAS NFO 260/260 존재를 뜻하지 않는다. 최신 NAS NFO 총수와 실제 필드 완전성은 **확인필요**. 과거 Stage8 **130/130 메타데이터·NFO 완료**와 현재 전체 260개를 혼동하지 않는다.
- **기존 정식 포스터 경로:** Stage8 85/85 PASS (WebP 83, JPEG 2) 기록은 유효하고 보호한다. **2026-11-04 실제 로컬 대표 이미지 조사:** 260개 중 201개 보유, **59개 미보유**. 웹 포스터·폴백 자동 연결 및 새 `cover.jpg` 실제 반영은 **미완료**.
- **기존 NFO 중복 방지:** 10월 30일 '129건 NFO 없음'은 **품번.nfo 이름만 확인한 오분류**로 확정, 해당 **129개 모두 유효한 `movie.nfo` 존재·XML/ID 검사 PASS**. 별도 사용자 승인으로 진행된 **기존 NFO 제목 접두사 보정 225건**, **추가 NFO 3건(MFCS-085, DANDYA-033, NHDTB-778)** 은 11월 2일까지 각각 완료·독립 readback PASS. 재생성하지 않는다.
- **실사용 NFO 자동화:** Stage9 10분 타이머 설정·자연 기동·신규 MBRBI-015 NFO 생성 및 Jellyfin 작품번호 표시 **한 작품 제품 시험 PASS(11월 2일)**. 11월 4~5일 포스터 진단에서는 전용 서비스·타이머 **중지 상태가 확인**되었으며, 과거 10분 운영 PASS를 현재 활성 상태로 오해하거나 무단 재시작하지 않는다.
- **현재 집중:** 기존 포스터 경로를 보존하고 정확한 작품의 Fourhoi JPEG만 `cover.jpg`로 이어 주는 **Stage9 자동 폴백 완성 → 오프라인 회귀 → 4개 작품 통합 시험**. `AT-099`, `DANDYA-033`, `FC2-PPV-3087371`, `FC2-PPV-4451371`만 대상으로 하고 `MBRBI-015`는 제외한다. Codex 11:56 KST 문서 커밋 `d7c0bdb443ba0eac31d008f56e54ba50e2b2b08f`까지 **구현 INCOMPLETE, 운영 쓰기 0**.

**최신 근거:** `docs/governance/stage9-media/ACTIVE_WORK.md`, `docs/handoff/missav-dlp-web/CURRENT_HANDOFF.md`, Stage9 계약 v1.0.7. 이 로드맵의 완료 표시는 해당 확인 범위만 닫고, 각 작업의 계약·승인 상태는 변경하지 않는다.

> 10월 30일 P03-H 상세 조사·대상·해시와 당시 보류 이력은 Git 기록 및 Stage9 ACTIVE_WORK에서 확인한다. 이 로드맵에서는 11월 2일의 실제 완료 결과를 현재 상태로 우선 표시한다.

## 1. 읽는 순서 및 업데이트 규칙

- 새 대화에서는 `AGENTS.md`, 공통 `docs/governance/PROJECT_CONTRACT.md`, 라우터 `docs/governance/ACTIVE_WORK.md`, 해당 영역의 `PROJECT_CONTRACT.md`와 `ACTIVE_WORK.md`를 먼저 확인한다. 이어 이 파일의 **현황·우선순위·다음 한 단계**를 읽는다.
- 이 파일은 사용자가 요청한 장기 작업 순서/진행 현황의 공용 기준이다. 개별 작업의 법적 승인·범위·실제 STATUS/TASK_ID는 각 ACTIVE_WORK와 계약 및 GitHub 정본이 우선한다. 이 문서의 다음 작업 표기는 새 구현·배포·NAS/DB/Jellyfin 쓰기 승인이 아니다.
- 진행 상태: **완료**=기재한 범위에 한해서 실제 결과가 확인됨, **진행 중**=착수했지만 범위별 완료 전, **미착수**=후속 예정, **보류**=추가 증거·사용자 결정·별도 승인 전 실행 금지. 독립 작업은 병렬로 진행할 수 있으나 위험도가 높고 미승인인 작업은 끼워 넣지 않는다.
- 새 작업이 생기면 본 순서를 기준으로 영향 영역/우선순위를 판단한다. 실제 완료 증거가 생길 때마다 해당 대화에서 즉시 행 상태를 **완료**로 바꾸고, 날짜·증거·커밋을 기록하며 `CURRENT_HANDOFF.md`에도 중요한 결과를 남긴다. 수행되지 않은 작업을 완료로 표시하거나, 채팅 사이에 자동 갱신되는 것으로 가정하지 않는다.
- 예전 Stage 번호는 이력/기술 식별자일 뿐이다. 사용자 대상 설명은 **영상 다운로드·저장 / 미디어 메타데이터·Jellyfin / 한국어 자막** 같은 기능명을 우선 사용한다. 기존 `stage9-media` 및 `stage11` 같은 계약·서비스·경로·작업 ID는 승인 없이 변경하지 않는다.
- 손상·삭제 위험이 있는 소스/운영 변경은 항상 안전 경계, 허용 파일·서비스, 기존 데이터 보존 조건, 정본 readback을 확인하고 필요 시 사용자 승인을 받은 뒤 실행한다.

## 2. 고정 우선순위 / 앞으로의 작업

| 순번 | ID | 기능별 작업 | 현재 상태 (2026-11-05) | 다음 단계 / 완료 조건 / 승인 |
| --- | --- | --- | --- | --- |
| 0 | P00 | **Stage9 포스터 자동화 완성 및 4개 작품 통합 시험** | **진행 중 — 구현 INCOMPLETE / 실전 4건 NOT_RUN** | 완료된 기존 메타데이터 기반 정식 포스터(형식별 `poster.*`) 보존 → URL 없거나 신뢰할 수 없는 경우 페이지·작품 일치 검증된 Fourhoi JPEG를 `cover.jpg` create-only → 둘 다 없으면 PENDING. 최소 오프라인 회귀 후 동일 경로로 정확한 4건 시험. 첫 신규 로컬 이미지의 Jellyfin 표시 확인을 통과한 뒤 나머지 3건. 운영 배포/쓰기 및 서비스 시작은 별도 승인. 260개 전체 재처리 금지. |
| 1 | P01 | **미디어 자동화 잔여 항목 원인 확인** (과거 Stage9 Media) | **완료 — 조사 범위 한정** | 2026-10-29 당시 CT108 읽기 전용 DB 확인: COMPLETED 122, FAILED 3, PENDING/RUNNING 0; 오래된 COMPLETED/UNKNOWN 조합 108, 포스터 PENDING 8건 모두 COVER_URL_MISSING, FNS-267 내부 Jellyfin CHECK_PENDING 1건, 당시 타이머 active 및 마지막 서비스 Result=success. 현재 타이머는 포스터 작업 중 중지 상태. 강제 재시도·정리·DB 변경은 별도 항목 P01-H로 **보류**. |
| 2 | P02 | **루트/Overlay 중복 파일 5쌍의 읽기 전용 정밀 검수** | **완료 — 정적 소스·패치 비교 범위만 (2026-10-29)** | 5쌍 모두 분석: HTML은 최종 Overlay 기준 UI/패치 순서, 저장 코드는 no-overwrite·SHA-256, 엔트리포인트는 HLS/MP4, 부트스트랩은 보호된 게시·복구, 앱은 영속 상태·재시도 안전성 차이가 핵심. 실제 빌드 중간 산출물과 새 단일 원본의 byte-identical 동등성은 미검증이며 P04 구현·검증 승인 시 별도 확인. 소스·이미지·운영 변경 0. |
| 3 | P03 | **NFO 작품번호 표시·Jellyfin 검색 및 신규 NFO 자동화** | **대표 제품 시험 PASS / 완료된 세부 작업 정리, 전체 일관성 확인필요** | 기존 `movie.nfo` 129개 존재·XML/ID PASS, 기존 NFO 품번 제목 보정 225건 PASS, 기존 누락 NFO 3건 복구 PASS, Stage9 10분 타이머·실제 신규 MBRBI-015 NFO/Jellyfin 표시 PASS(11/02), EBWH-350 실제 품번 검색 PASS(10/30). **완료한 NFO를 재생성하지 않는다.** 전체 260개 NAS NFO/필드 완전성은 아직 조사 안 됨. 잔여 예외만 별도 범위 승인 뒤 처리; 타이머는 현재 포스터 작업 중지 상태 유지. |
| 4 | P04 | **검수로 확정된 중복만 단계적 단일 원본화** | **미착수 — 범위/구현 승인 전** | P02 결과로 각 파일의 patch 의존성, 실행 동등성, 데이터 보호 경계를 문서화하고 승인된 파일에만 변경→격리 검증→별도 운영 배포 승인. 위험도가 낮은 HTML부터 제안하되 확정 우선순위는 검수 결과에 따른다. |
| 5 | P05 | **일반 다운로드/Discovery Writer 작업 DLDWS-001 종료 조건 점검** | **미착수 — 대표 운영 검증 PASS** | 이미 완료한 Docker 이미지 교체·FNS-267 실사용 성공을 재검증 없이 활용한다. 남은 계약상 미완료 조건과 Writer 소켓 안전성 이력만 정리하고 사용자 결정 후 종료 여부 판단. 현재 두 영역 모두 `IN_PROGRESS / DLDWS-001`. |
| 6 | P06 | **한국어 자막 음성 인식/화자 근거 확인** (이전 Stage11) | **진행 중 — 별도 독립 작업** | 현재 `S11-WX011 / IN_PROGRESS`. 기존 S04/S08/S13 일본어 후보와 오디오를 사용자에게 비교 제시할 다음 결정이 남아 있음. S03/S11/S15 누락 의심, 일본어 정답/정확한 경계/화자 DER는 UNKNOWN. 계약에 따른 읽기 전용 범위만. |
| 7 | P07 | **한국어 자동 자막 품질·게시 최종 완성** | **미착수/후속 승인 필요** | 외부 JA+ASR 증거, 누락 대화 회복, 자연스러운 Hermes 번역/문장·화자 경계와 Stage12 안전 게시까지 제품 품질 입증 필요. 설계 우선순위 충돌은 사용자 결정, 자막 생성·실행·게시는 별도 승인. |
| 8 | P08 | **파일 관리: 보유 라이브러리 요약·라이브러리 DB 현황 화면 개편** | **요구사항 등록 완료 / 구현 미착수 — P00 이후** | 상단 요약: 전체 작품 수 / 한국어 자막 / 메타데이터 / 포스터 / 전체 라이브러리 용량. 기존 `자막 처리 현황` 탭 명칭을 `라이브러리 DB 현황`(가칭)으로 바꾸고 하위에 자막 처리 현황 / 메타데이터 처리 현황 / 포스터 처리 현황을 배치. 기존 자막 미해결·자막 없음 세부 현황은 자막 섹션 안에 보존. 실제 파일·DB의 의미와 일치하는 집계 정의·UI/API 구현/검증은 별도 승인. |

### 이후 UI 개편 요구 — P08 (설계 기록만, 구현 미승인)

- **파일 관리 → 보유 라이브러리:** 요약 카드 5개 — `전체 작품 수`, `한국어 자막`, `메타데이터`, `포스터`, `전체 라이브러리 용량`. 상단에서는 `자막 미해결`, `자막 없음`을 빼되 해당 정보·필터를 삭제하지 않고 세부 자막 현황에 유지한다.
- **파일 관리 → `자막 처리 현황` 탭 → `라이브러리 DB 현황`(가칭):** `자막 처리 현황` / `메타데이터 처리 현황` / `포스터 처리 현황` 3개 섹션. 각 영역에서 완료·미완료·진행/실패·보류와 원인을 확인할 수 있도록 설계한다. 세부 UI 구성과 명칭은 구현 전 확정한다.
- **집계 원칙:** `메타데이터`는 단순 `titles` DB 행 개수가 아니라 **실제 NFO 존재와 유효 상태를 구분**한다. `포스터`는 NAS에 존재하는 Jellyfin 대표 이미지(`poster.*`, `cover.*`, 기타 인정 Primary)로 집계하고 `thumb.jpg`만 있는 경우 완료로 속이지 않는다. 자막·용량도 현재 실제 보유 작품 기준으로 집계하되, DB 상태와 NAS 현황이 다르면 **확인필요/HOLD**를 구분한다. 서버 전체 재스캔을 UI 요청마다 반복하거나 완료된 미디어를 재생성하지 않는다.
- **보존 조건:** PC·모바일 반응형 UI 및 기존 파일 관리 `재생`·`다운로드`·`삭제` 동작 유지. 현재는 로드맵 기록만. 실제 UI/API 구현은 Downloader 및 관련 Stage9/자막 정보 소비 경계를 계약·라우팅으로 확인한 뒤 별도 승인한다. 기존 Stage11 자막 파이프라인 자체를 개편하는 작업은 아니다.

### 남은 보류 / 과거 조사 기록 (2026-11-02 완료 증거가 10-30 당시 기록에 우선)

- **P01-H:** 운영 오류/DB 상태 재정리: 10-29 당시 실패 작업·PENDING 등의 분석 이력은 유지. 11-02 세 작품(MFCS-085, DANDYA-033, NHDTB-778)의 **실제 NFO 파일 복구는 완료/PASS**. 과거 media_jobs 실패 카운터/상태까지 수리됐다는 증거는 없으므로 DB 재시도·초기화·광역 정리는 별도 승인 전 보류.
- **P03-H:** 기존 NFO 품번 제목 보정은 정확한 **225개(188+37) 완료/PASS**, 백업·독립 검증 완료(11-02). 추가 기존 NFO 누락 세 작품도 별도 승인으로 복구·독립 검증 PASS. EBWH-350 제목·품번 검색은 대표 1건 PASS. 그 밖의 소유권/품번 충돌/전체 일관성은 별도 증거 없이 완료로 확대하지 않는다.
- **P03-M:** 10-30 'NFO 미존재 133'은 `<ID>.nfo` 기준 초기 판정. **129개에 `movie.nfo`가 이미 존재했고 XML/ID 검증 PASS**이므로 해당 129건은 실제 NFO 누락이 아니었다. 나머지 3건은 11-02 개별 복구 PASS; 과거 시차 1건은 최신 전체 파일 실측 확인필요. 잘못 분류된 129건의 신규 NFO 재생성 금지.
- **P03-N:** NFO-only 129건 신규 생성 소스는 과거 정본 승격 이력이 있지만, 실제 129개 모두 `movie.nfo`가 있어 **그 129개 신규 생성은 필요 없음 / 적용 차단이 정상**. 이 구현의 실제 129건 NAS 적용은 하지 않았고 앞으로도 기존 파일을 중복 생성하지 않는다.
- **P03-T:** **10분 전용 타이머 배포·자연 실행 PASS(11-02)**, 신규 MBRBI-015 다운로드 후 자동 NFO/Jellyfin 작품번호 표시 제품 시험 PASS(대표 1건). 이후 11-04~05 포스터 시험 중 서비스·타이머는 중지 상태가 확인됨. 다시 시작하거나 타이머를 바꾸는 작업은 별도 운영 승인 전 금지.
- 재생 정상 파일의 대체 코덱/Jellyfin 강제 트랜스코딩, 1회성 iPhone Safari 다운로드 실패 등 과거 선택적 기능은 재현/필요성 증거 없이는 후순위.
- 과거 Stage10의 보유목록/중복방지 등 완료 이력은 새 작업으로 재등록하지 않는다. 2026-10-29 최신 라우터에 별도 Stage10 workstream은 없다.

## 3. 완료 이력 — 다시 진행하지 않음

| ID | 작업 | 판정/증거 |
| --- | --- | --- |
| D01 | 일반 Downloader·PC/모바일 UI 및 PWA의 기존 완료 작업 | 이전 운영/핸드오프의 CLOSED 범위만 완료. 새 전체 품질 보장은 아님. |
| D02 | 미디어 자동화 File Station 전환 및 전용 타이머 대표 검증 | 2026-10-28 공동 운영 전환 CLOSE; PPPE-446, SNOS-403, FNS-258 NFO/포스터/Jellyfin 대표 결과 PASS. `stage9-media` 영역 상태 자체는 `IN_PROGRESS`. |
| D03 | `teddy_downloader_admin.py` 및 `teddy_routing.py` 단일 원본화 | GitHub 승격 및 기존 관련 검증 완료. 재구현 금지. |
| D04 | `teddy_generic.py` 단일 원본화 | 원본 SHA-256 `a5ea703022bcfaf50878e49e5eac47e75eb1dcaab979024e4b22119dfcac7c07`; 기존 Overlay 중복 제거 완료. |
| D05 | Python 3.10 Docker 신규 이미지 빌드·운영 배포 | 2026-10-29 새 이미지 `sha256:ba31ba9cfcc481dc1f658312a3155a3496856008ff4d52f5a652de0766fd0dbe` 운영 DEPLOY/HTTP/MANIFEST/PRESERVED-SIDECARS PASS; 기존 이미지·롤백 자료 보존. 롤백 *실행* 테스트는 아님. |
| D06 | FNS-267 다운로드→MP4 변환→NAS 저장→포스터/NFO 존재→Jellyfin 재생 | 2026-10-29 사용자 직접 확인 PASS (작품 한 건의 E2E, 모든 제목/파일 내용 품질 확인은 아님). |
| D07 | 미디어 자동화 미완료·오류 원인 구분 | 2026-10-29 CT108 DB/타이머 읽기 전용 점검 완료; 실제 미해결 운영 처리와 분리하여 P01-H로 보류. |
| D08 | 기존 NFO 품번 제목 보정 및 3개 NFO 복구 | **225개 품번 제목 보정 + MFCS-085/DANDYA-033/NHDTB-778 신규 sidecar 3개** 실제 운영 적용·별도 NAS 검증 PASS (2026-11-02). 원본 백업 보존. |
| D09 | P03 10분 타이머와 신규 다운로드 NFO 대표 제품 시험 | **2026-11-02 10분 타이머 설정·자연 실행 PASS**, MBRBI-015 신규 NFO NAS 확인·Jellyfin 작품번호 표시 PASS. 현재 타이머 active를 의미하지 않음. |
| D10 | 보유작품 메타데이터 행 및 로컬 대표 이미지 갭 현황 | **2026-11-05 Discovery 260/260 제목 행/유효 JSON PASS**, **2026-11-04 NAS Primary 201/260 존재, 59/260 없음 PASS**. NFO 실제 존재 260/260이나 poster 자동 폴백 완성을 뜻하지 않음. |
| D11 | 기존 정식 포스터 경로 및 MBRBI-015 과거 예외 | Stage8 **85/85 포스터 PASS (WebP 83/JPEG 2)**, MBRBI-015 1회성 NAS thumb + Jellyfin API 변경/사용자 화면 확인 PASS. 새 `cover.jpg` 로컬 파일 자동 인식 통합 시험과는 별개. |

## 4. 현재 검수 기준선: P02 / HTML

- 정본에서 동일 경로가 root와 `downloader_runtime_overlay/` 아래에 **총 5쌍** 존재하고 모두 Git blob이 달랐다. 나머지는 `teddy_storage.py`, `teddy_entrypoint.py`, `teddy_bootstrap.py`, `app.py`. 해당 목록은 특정 경로 쌍 비교 결과이며 전체 프로젝트 모든 중복 가능성을 증명하지는 않는다.
- `templates/index.html`: root 4 `data-page`/67 ID/3 script/3 CSS, Overlay 6 `data-page`/91 ID/11 script/9 CSS; Overlay에 browser/logs와 추가 UI 제어 요소가 있다.
- Dockerfile은 중간 root HTML에 여러 `teddy_patch_*.py`와 sed 변경을 적용한 **이후** 최종 `COPY downloader_runtime_overlay/ /app/`로 Overlay HTML을 적용한다. 따라서 Overlay 삭제는 안전한 중복 제거가 아니다. 실제 빌드 최종 HTML과 새 원본의 동등성 검증, 기존 패치 적용 가능성 검증이 필요.
- **2026-10-29 HTML 정적 패치/검증 체인 검수: 부분 완료.** Dockerfile은 `teddy_patch_index.py`, `teddy_patch_logs.py`, `teddy_patch_storage.py`, `teddy_patch_routing.py`, `teddy_patch_ytdlp_options.py`, `teddy_patch_browser.py`, `teddy_patch_mobile.py` 및 `teddy_patch_pwa.py` 등을 사용해 root HTML을 수정한다. 그 이후 최종 Overlay COPY가 적용되므로 중간 root HTML과 실행 HTML을 같은 것으로 간주하면 안 된다.
- 최종 Overlay HTML은 이미지 manifest에 `templates/index.html` SHA-256 `4d379e37c76e25781ea4eda8d169af5f24d70a4d53ef74808dc088c37b85766f`로 지정되어 있으며, 2026-10-29 실제 배포 시 최종 manifest 검증 PASS. 마지막 COPY 뒤 `teddy_file_management_navigation_smoke.py`와 `teddy_library_ui_smoke.py`는 실행되지만 `teddy_discovery_ui_shell_smoke.py`·`teddy_subtitle_status_ui_smoke.py`는 COPY 전 단계에서 실행된다. 따라서 **최종 UI에 관한 모든 경계를 검증했다고 주장하지 않는다.**
- **정적 차이 검수 결과 (2026-10-29):** 최종 Overlay HTML은 기존 root의 HTML ID를 모두 포함하며 별도 브라우저/로그 화면, 추가 자산을 포함한다. Dockerfile의 `teddy_patch_mobile.py`는 직접 실행되지 않고, 모바일 CSS 순서는 별도의 inline `sed`로 조정된다. Docker 최종 복사 전과 후에 실행되는 UI smoke 종류가 달라 새 통합 빌드에는 검증 보강이 필요하다. 소스 패치 후의 **중간 HTML 전체 bytes를 별도 확보·비교하지는 않았다**.
- **저장:** root/Overlay 공통 top-level 정의 43개 중 4개 변경, Overlay-only `_ssh_remote_sha256` 1개; 충돌 시 덮어쓰기 방지 (`os.replace`→no-clobber link), 원본·원격 해시 검증, 재시작 게시 증거 및 오류 구분을 보존해야 한다.
- **다운로드 진입점:** 10개 top-level 함수 중 4개 변경; HLS 세그먼트 안전 저장/매니페스트, 비동기 처리, MP4 큐·일시정지·재시도 경계가 Overlay에 있으며 root 단독 사용 불가.
- **부트스트랩:** 변경된 top-level 함수 5개와 Overlay-only 함수 4개(분석한 정의 기준); 완료파일 게시 복구·안전 잠금·저장 오류에 따른 무의미한 네트워크 fallback 차단·MP4 큐 보호 경계 보존이 필요.
- **앱:** 변경된 top-level 함수 10개와 Overlay-only 함수 9개(분석한 정의 기준); 작업 상태 파일의 안전한 저장·복구, retry 큐 등록 원자성, 건강 검사 모드, MP4 상태 보호 경계가 있어 통합 변경은 고위험.
- **판정:** P02는 **정적 소스/패치 차이 검수 범위에 한해 완료**. 새 이미지에서 동등 실행 테스트, 빌드 중간 결과 byte 비교, 원본 통합 변경·배포는 **NOT_RUN / 미승인(P04)**. 지금까지 동작 중인 Overlay를 임의 삭제하거나 root로 되돌리지 않는다. **현재 제품 집중 순서는 P00 Stage9 포스터 자동 폴백 완성 → 4개 작품 통합 시험**이다. P03의 검증된 NFO 제품 결과를 다시 수행하지 않는다. UI 개편 P08은 이후이며 P04 같은 별도 작업은 사용자가 우선순위를 바꾸지 않는 한 착수하지 않는다.

## 5. 정확한 진행 현황의 원천

- 작업 등록/계약: `docs/governance/ACTIVE_WORK.md` 및 각 `docs/governance/<workstream>/ACTIVE_WORK.md`.
- 장기 운영 인계와 과거 증거: `docs/handoff/missav-dlp-web/CURRENT_HANDOFF.md`.
- 2026-10-28 정리 근거: `TEDDY_DOWNLOADER_ROUTING_PROMOTION_MASTER_HANDOFF_20261028.md` (사용자 제공 이력; 승인 대체 불가).
- **이 파일이 작업 우선순위/상태의 시작점이며, 각 작업의 실제 승인·원격 코드·운영 사실 확인을 대신하지 않는다.**
