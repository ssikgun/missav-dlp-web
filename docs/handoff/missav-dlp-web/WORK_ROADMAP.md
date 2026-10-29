# Teddy Downloader — 살아 있는 작업 로드맵 (WORK_ROADMAP)

ROADMAP_VERSION: 1
UPDATED_AT: 2026-10-29 KST
CANONICAL_REPO: ssikgun/missav-dlp-web
CANONICAL_BRANCH: teddy-subtitle-stage11
TRACKER_STATUS: ACTIVE — informational progress and priorities, NOT a task authorization

## 1. 읽는 순서 및 업데이트 규칙

- 새 대화에서는 `AGENTS.md`, 공통 `docs/governance/PROJECT_CONTRACT.md`, 라우터 `docs/governance/ACTIVE_WORK.md`, 해당 영역의 `PROJECT_CONTRACT.md`와 `ACTIVE_WORK.md`를 먼저 확인한다. 이어 이 파일의 **현황·우선순위·다음 한 단계**를 읽는다.
- 이 파일은 사용자가 요청한 장기 작업 순서/진행 현황의 공용 기준이다. 개별 작업의 법적 승인·범위·실제 STATUS/TASK_ID는 각 ACTIVE_WORK와 계약 및 GitHub 정본이 우선한다. 이 문서의 다음 작업 표기는 새 구현·배포·NAS/DB/Jellyfin 쓰기 승인이 아니다.
- 진행 상태: **완료**=기재한 범위에 한해서 실제 결과가 확인됨, **진행 중**=착수했지만 범위별 완료 전, **미착수**=후속 예정, **보류**=추가 증거·사용자 결정·별도 승인 전 실행 금지. 독립 작업은 병렬로 진행할 수 있으나 위험도가 높고 미승인인 작업은 끼워 넣지 않는다.
- 새 작업이 생기면 본 순서를 기준으로 영향 영역/우선순위를 판단한다. 실제 완료 증거가 생길 때마다 해당 대화에서 즉시 행 상태를 **완료**로 바꾸고, 날짜·증거·커밋을 기록하며 `CURRENT_HANDOFF.md`에도 중요한 결과를 남긴다. 수행되지 않은 작업을 완료로 표시하거나, 채팅 사이에 자동 갱신되는 것으로 가정하지 않는다.
- 예전 Stage 번호는 이력/기술 식별자일 뿐이다. 사용자 대상 설명은 **영상 다운로드·저장 / 미디어 메타데이터·Jellyfin / 한국어 자막** 같은 기능명을 우선 사용한다. 기존 `stage9-media` 및 `stage11` 같은 계약·서비스·경로·작업 ID는 승인 없이 변경하지 않는다.
- 손상·삭제 위험이 있는 소스/운영 변경은 항상 안전 경계, 허용 파일·서비스, 기존 데이터 보존 조건, 정본 readback을 확인하고 필요 시 사용자 승인을 받은 뒤 실행한다.

## 2. 고정 우선순위 / 앞으로의 작업

| 순번 | ID | 기능별 작업 | 상태 (2026-10-29) | 다음 단계 / 완료 조건 / 승인 |
| --- | --- | --- | --- | --- |
| 1 | P01 | **미디어 자동화 잔여 항목 원인 확인** (과거 Stage9 Media) | **완료 — 조사 범위 한정** | CT108 읽기 전용 DB 확인: COMPLETED 122, FAILED 3, PENDING/RUNNING 0; 오래된 COMPLETED/UNKNOWN 조합 108, 포스터 PENDING 8건 모두 COVER_URL_MISSING, FNS-267 내부 Jellyfin CHECK_PENDING 1건, 타이머 active 및 마지막 서비스 Result=success. 강제 재시도·정리·DB 변경은 별도 항목 P01-H로 **보류**. |
| 2 | P02 | **루트/Overlay 중복 파일 5쌍의 읽기 전용 정밀 검수** | **진행 중 — 현재 우선 수행** | 먼저 `templates/index.html`에서 빌드 중간 패치·최종 Overlay/실사용 기능 차이와 위험을 확인하고 나머지 `teddy_storage.py` → `teddy_entrypoint.py` → `teddy_bootstrap.py` → `app.py`를 차례로 검수. 기능 손실 없는 통합 가능성/관련 workstream을 분류한다. 이 단계는 소스·이미지 수정 없음. |
| 3 | P03 | **Jellyfin에서 `[작품번호] 작품 제목` 표시 및 작품번호 검색** (미디어 메타데이터) | **미착수 — 신규 요구 등록 / 구현 별도 승인 필요** | 현재 NFO `<title>`에는 제목만, `<id>`/`<uniqueid type="dvd_id">`에는 품번이 저장됨. 후보는 신규 NFO 생성 시 제목에 대괄호 품번을 단 한 번 접두하고 실제 제목/원제·고유 ID 보존. 독립 테스트와 신규 작품 1건 Jellyfin 검색·표시 검증 후 확대 여부 결정. **기존 NAS NFO 일괄 덮어쓰기·자동 Refresh 금지.** |
| 4 | P04 | **검수로 확정된 중복만 단계적 단일 원본화** | **미착수 — 범위/구현 승인 전** | P02 결과로 각 파일의 patch 의존성, 실행 동등성, 데이터 보호 경계를 문서화하고 승인된 파일에만 변경→격리 검증→별도 운영 배포 승인. 위험도가 낮은 HTML부터 제안하되 확정 우선순위는 검수 결과에 따른다. |
| 5 | P05 | **일반 다운로드/Discovery Writer 작업 DLDWS-001 종료 조건 점검** | **미착수 — 대표 운영 검증 PASS** | 이미 완료한 Docker 이미지 교체·FNS-267 실사용 성공을 재검증 없이 활용한다. 남은 계약상 미완료 조건과 Writer 소켓 안전성 이력만 정리하고 사용자 결정 후 종료 여부 판단. 현재 두 영역 모두 `IN_PROGRESS / DLDWS-001`. |
| 6 | P06 | **한국어 자막 음성 인식/화자 근거 확인** (이전 Stage11) | **진행 중 — 별도 독립 작업** | 현재 `S11-WX011 / IN_PROGRESS`. 기존 S04/S08/S13 일본어 후보와 오디오를 사용자에게 비교 제시할 다음 결정이 남아 있음. S03/S11/S15 누락 의심, 일본어 정답/정확한 경계/화자 DER는 UNKNOWN. 계약에 따른 읽기 전용 범위만. |
| 7 | P07 | **한국어 자동 자막 품질·게시 최종 완성** | **미착수/후속 승인 필요** | 외부 JA+ASR 증거, 누락 대화 회복, 자연스러운 Hermes 번역/문장·화자 경계와 Stage12 안전 게시까지 제품 품질 입증 필요. 설계 우선순위 충돌은 사용자 결정, 자막 생성·실행·게시는 별도 승인. |

### 별도 보류 / 자동 수행하지 않는 항목

- **P01-H — 미디어 자동화 잔여 운영 처리:** `DANDYA-033`, `NHDTB-778` = unsupported video extension (각 실패 5회), `MFCS-085` = cover_url missing (과거 누적 17,161회); 포스터 대기 8건은 URL 없음; `FNS-267`은 Jellyfin 실제 재생 PASS지만 DB의 recovery/visibility PENDING이 관찰됨. 이전 완료 108건의 신규 필드 UNKNOWN은 미처리 108건이라고 단정하지 않는다. 처리를 원하면 최신 상태 읽기 전용 재확인 후 안전한 별도 승인. **보류**.
- **P03-H — 과거 NFO 전체 일괄 수정:** 기존 NFO는 File Station create-only/no-overwrite 규칙에 묶여 있으므로 새 규칙 도입과 분리한다. **보류 / 명시적 쓰기 승인 필요**.
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

## 4. 현재 검수 기준선: P02 / HTML

- 정본에서 동일 경로가 root와 `downloader_runtime_overlay/` 아래에 **총 5쌍** 존재하고 모두 Git blob이 달랐다. 나머지는 `teddy_storage.py`, `teddy_entrypoint.py`, `teddy_bootstrap.py`, `app.py`. 해당 목록은 특정 경로 쌍 비교 결과이며 전체 프로젝트 모든 중복 가능성을 증명하지는 않는다.
- `templates/index.html`: root 4 `data-page`/67 ID/3 script/3 CSS, Overlay 6 `data-page`/91 ID/11 script/9 CSS; Overlay에 browser/logs와 추가 UI 제어 요소가 있다.
- Dockerfile은 중간 root HTML에 여러 `teddy_patch_*.py`와 sed 변경을 적용한 **이후** 최종 `COPY downloader_runtime_overlay/ /app/`로 Overlay HTML을 적용한다. 따라서 Overlay 삭제는 안전한 중복 제거가 아니다. 실제 빌드 최종 HTML과 새 원본의 동등성 검증, 기존 패치 적용 가능성 검증이 필요.
- **2026-10-29 HTML 정적 패치/검증 체인 검수: 부분 완료.** Dockerfile은 `teddy_patch_index.py`, `teddy_patch_logs.py`, `teddy_patch_storage.py`, `teddy_patch_routing.py`, `teddy_patch_ytdlp_options.py`, `teddy_patch_browser.py`, `teddy_patch_mobile.py` 및 `teddy_patch_pwa.py` 등을 사용해 root HTML을 수정한다. 그 이후 최종 Overlay COPY가 적용되므로 중간 root HTML과 실행 HTML을 같은 것으로 간주하면 안 된다.
- 최종 Overlay HTML은 이미지 manifest에 `templates/index.html` SHA-256 `4d379e37c76e25781ea4eda8d169af5f24d70a4d53ef74808dc088c37b85766f`로 지정되어 있으며, 2026-10-29 실제 배포 시 최종 manifest 검증 PASS. 마지막 COPY 뒤 `teddy_file_management_navigation_smoke.py`와 `teddy_library_ui_smoke.py`는 실행되지만 `teddy_discovery_ui_shell_smoke.py`·`teddy_subtitle_status_ui_smoke.py`는 COPY 전 단계에서 실행된다. 따라서 **최종 UI에 관한 모든 경계를 검증했다고 주장하지 않는다.**
- **바로 다음 행동:** 기존 정본·빌드 증거에서 **중간 root 패치 결과와 최종 Overlay HTML의 차이**를 분류해 변경 없이 동일 최종 결과를 만들 수 있는 최소 구현안을 정의한다. 다른 영역의 UI 경계(특히 자막 상태)는 관련 workstream 승인 여부를 먼저 확인한다. 이미지 재빌드/실제 코드 수정은 현재 승인되지 않았다.

## 5. 정확한 진행 현황의 원천

- 작업 등록/계약: `docs/governance/ACTIVE_WORK.md` 및 각 `docs/governance/<workstream>/ACTIVE_WORK.md`.
- 장기 운영 인계와 과거 증거: `docs/handoff/missav-dlp-web/CURRENT_HANDOFF.md`.
- 2026-10-28 정리 근거: `TEDDY_DOWNLOADER_ROUTING_PROMOTION_MASTER_HANDOFF_20261028.md` (사용자 제공 이력; 승인 대체 불가).
- **이 파일이 작업 우선순위/상태의 시작점이며, 각 작업의 실제 승인·원격 코드·운영 사실 확인을 대신하지 않는다.**
