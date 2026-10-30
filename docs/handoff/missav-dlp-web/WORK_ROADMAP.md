# Teddy Downloader — 살아 있는 작업 로드맵 (WORK_ROADMAP)

ROADMAP_VERSION: 1
UPDATED_AT: 2026-10-30 KST (P03-N EXACT_ONE_TARGET_PREFLIGHT_PHASE1=PASS_SNAPSHOT_AND_DB_129, HISTORICAL_MISSING_ID_INTERSECTION=NEXT, NAS_GETINFO=NOT_RUN, NFO_UPLOAD=NOT_APPROVED, P03-T_LAST_PLANNED)
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
| 2 | P02 | **루트/Overlay 중복 파일 5쌍의 읽기 전용 정밀 검수** | **완료 — 정적 소스·패치 비교 범위만 (2026-10-29)** | 5쌍 모두 분석: HTML은 최종 Overlay 기준 UI/패치 순서, 저장 코드는 no-overwrite·SHA-256, 엔트리포인트는 HLS/MP4, 부트스트랩은 보호된 게시·복구, 앱은 영속 상태·재시도 안전성 차이가 핵심. 실제 빌드 중간 산출물과 새 단일 원본의 byte-identical 동등성은 미검증이며 P04 구현·검증 승인 시 별도 확인. 소스·이미지·운영 변경 0. |
| 3 | P03 | **Jellyfin에서 `[작품번호] 작품 제목` 표시 및 작품번호 검색** (미디어 메타데이터) | **과거 보유 작품 NFO-only 4파일 정본 소스 승격 PASS; 운영 배포·실제 생성·기존 NFO 수정은 미실행, Jellyfin 검색 미검증** | 신규 NFO 생성 코드 정본 승격 `b31873824527bbcdf800d141b40eaf6e2af03abd`, Stage9 전용 배포 PASS, 자연 실행 PASS(10:01:16 KST; 미디어 처리 0). 255개 보유 중 NFO 존재 122개(119개 품번 추가 후보, 3개 다른 품번 충돌), NFO 부재 133개. 부재 133개 원인: 129개는 provenance 필터(`library-inventory` 68, `organizer-apply` 61), 3개 실패/재시도 한도, 1개 DB NFO 완료 대 과거 NAS 파일 부재. **순서:** (1) P03-N NFO-only/create-only **설계 PASS**, Synology 업로드 충돌 오류 1805/모의 414 차이와 실 NAS 동시 생성 보호는 확인 필요 → (2) **v2 4파일 GitHub 정본 소스만 승격 PASS (`fc8671487a7a1adb033619b58878f6bddb0c5d48`), 1건 읽기 전용 점검 1차 PASS(감사 스냅샷 3파일+현재 DB 68/61), 과거 누락 ID 교집합 확인·1건 NAS 확인은 미실행, 운영 배포·NAS 실제 생성 별도 승인 필요**, 이후 결과 검수와 별도 승인된 정본 승격·정확한 1건 시험 생성 및 133 누락 항목 분리 처리 → (3) 기존 119개 NFO `<title>` 수정 안전 경로 설계/검증·별도 승인된 적용(13 소유권 불일치와 3 품번 충돌 보호) → (4) 실제 Jellyfin 품번 검색 검증 → (5) **P03 마지막 작업: Stage9 1시간→10분 전용 타이머 변경**(별도 승인/검증 전 NOT_RUN). 영상/기존 포스터·provenance/Organizer/다른 타이머 보호. |
| 4 | P04 | **검수로 확정된 중복만 단계적 단일 원본화** | **미착수 — 범위/구현 승인 전** | P02 결과로 각 파일의 patch 의존성, 실행 동등성, 데이터 보호 경계를 문서화하고 승인된 파일에만 변경→격리 검증→별도 운영 배포 승인. 위험도가 낮은 HTML부터 제안하되 확정 우선순위는 검수 결과에 따른다. |
| 5 | P05 | **일반 다운로드/Discovery Writer 작업 DLDWS-001 종료 조건 점검** | **미착수 — 대표 운영 검증 PASS** | 이미 완료한 Docker 이미지 교체·FNS-267 실사용 성공을 재검증 없이 활용한다. 남은 계약상 미완료 조건과 Writer 소켓 안전성 이력만 정리하고 사용자 결정 후 종료 여부 판단. 현재 두 영역 모두 `IN_PROGRESS / DLDWS-001`. |
| 6 | P06 | **한국어 자막 음성 인식/화자 근거 확인** (이전 Stage11) | **진행 중 — 별도 독립 작업** | 현재 `S11-WX011 / IN_PROGRESS`. 기존 S04/S08/S13 일본어 후보와 오디오를 사용자에게 비교 제시할 다음 결정이 남아 있음. S03/S11/S15 누락 의심, 일본어 정답/정확한 경계/화자 DER는 UNKNOWN. 계약에 따른 읽기 전용 범위만. |
| 7 | P07 | **한국어 자동 자막 품질·게시 최종 완성** | **미착수/후속 승인 필요** | 외부 JA+ASR 증거, 누락 대화 회복, 자연스러운 Hermes 번역/문장·화자 경계와 Stage12 안전 게시까지 제품 품질 입증 필요. 설계 우선순위 충돌은 사용자 결정, 자막 생성·실행·게시는 별도 승인. |

### 별도 보류 / 자동 수행하지 않는 항목

- **P01-H — 미디어 자동화 잔여 운영 처리:** `DANDYA-033`, `NHDTB-778` = unsupported video extension (각 실패 5회), `MFCS-085` = cover_url missing (과거 누적 17,161회); 포스터 대기 8건은 URL 없음; `FNS-267`은 Jellyfin 실제 재생 PASS지만 DB의 recovery/visibility PENDING이 관찰됨. 이전 완료 108건의 신규 필드 UNKNOWN은 미처리 108건이라고 단정하지 않는다. 처리를 원하면 최신 상태 읽기 전용 재확인 후 안전한 별도 승인. **보류**.
- **P03-H — 기존 NFO 제목 품번 추가:** **255개 전체 NFO 인벤토리 완료 (2026-10-30 Codex 보고)**. NFO 122개 중 119개는 올바른 ID 메타데이터와 XML을 갖지만 `<title>`에 `[DVD-ID]` 접두사 없음; 3개는 다른 품번 접두사로 별도 판별 필요. 119개 중 영상/NFO 소유자·그룹 불일치 13개 별도 보호. 전체 NFO 없는 133개는 P03-M에서 원인별 분류 완료(129 provenance 필터·3 실패 한도·1 DB/과거 NAS 상태 불일치). **119개 기존 제목 수정 목표 사용자 사전 승인**; 기존 File Station create-only로 수정 수단 **BLOCKED/운영 적용 NOT_STARTED**. 원본 백업·해시·원자적 교체·소유권 검증 필요. 포스터 존재 수는 별도 조사하지 않아 UNKNOWN.
- **P03-M — NFO 미존재 133개 원인 분석:** **CT108 읽기 전용 원인별 분류 PASS (2026-10-30 사용자 로그)**. 이전 NAS 인벤토리에서 NFO 없는 133개 중 129개는 현재 `media_jobs` 미등록이며, Stage9 등록 조건 중 오직 `holdings.discovered_by='completion-stage9'`가 불일치: **`library-inventory` 68개 + `organizer-apply` 61개**. 두 출처 모두 영상 보유(`storage_root='jav'`, `present=1`)와 Organizer `COMPLETED` 조건 충족. 즉 현재 자동화가 등록하지 않는 이유는 출처 필터, 실제 과거 NFO 미생성의 모든 인과는 별도. 그 외 3개는 media job FAILED/재시도 한도, 1개는 media job NFO COMPLETE지만 **과거** NAS 확인 시 누락(현시점 파일 상태 재확인 필요). NFO 신규 생성이나 재시도 대상 변경 없이 **역사적 보유 자료의 `discovered_by`를 보존하는 NFO-only create-only 경로 설계 제안**. 전수 129건 자동 실행, provenance 변경, 소유권 우회는 미승인. 기존 119개 제목 수정 안전 교체도 BLOCKED / 미실행. Jellyfin 품번 검색 NOT_VERIFIED; P03-T Stage9 10분 타이머는 P03 마지막 단계에 유지 / 변경 미실행.
- **P03-N — 과거 보유 129개 NFO 신규 생성:** **v2 4파일 GitHub 정본 소스-only 승격 PASS (2026-10-30) / 운영 배포 및 실 NAS 생성 미승인·NOT_RUN**. 사용자 별도 승인을 기록한 뒤 정확한 검수 패치 `p03n-review-v2-twr9OL.patch` 15,692B SHA-256 `85a292816c3c457d6b712d8b62d1961afc1d1d72d69f7be70e2732f914a44802`의 4 Git blob SHA를 검증, 하나의 원자적 source commit `fc8671487a7a1adb033619b58878f6bddb0c5d48`으로 정본 `teddy-subtitle-stage11`에 승격. GitHub HEAD/4파일 읽기-back·커밋 diff EXACT-4 PASS; 신규 합성 33·File Station 회귀 6 PASS는 Codex 보고 및 v2 독립 정적 검수 PASS_OFFLINE, 신규 독립 실행은 없음. NFO-only는 2개 역사적 provenance/Organizer 완료/작품번호·제목 메타데이터·영상 경로·크기/소유권 조건과 기존 NFO 충돌 정지를 사용하되 **실제 129개 대상은 DB/NAS에서 아직 확인하지 않음**. `LIVE_CREATE_ONLY_GUARD=UNVERIFIED`, 실제 NFO 현재 부재·영상 owner/group 독립 검증·실 NAS File Station 동시 생성 보호는 확인 필요. **다음(사용자 승인됨):** 과거 NFO 누락 감사 스냅샷을 확인해 정확한 DVD-ID **1건 선택 → 해당 1건만 운영 DB/NAS 읽기 전용 사전점검**. 1차 CT108 점검에서 감사 스냅샷 `summary.json`·`targets.jsonl`·`inventory.jsonl` 존재/형식 PASS, 실 DB `mode=ro`+`query_only=ON` 현재 적격군 `library-inventory` 68건 + `organizer-apply` 61건 확인(합계 129). 단 기존 129개 NFO 누락 ID 집합과의 **실제 교집합은 아직 미확인**이고 감사 첫 샘플은 NFO가 존재하는 작품임. **다음:** 감사 `inventory.jsonl`의 `nfo_present=false` 작품을 `targets.jsonl` 및 현재 DB 적격군과 정확한 ID·경로로 대조, 1개 DVD-ID 선정 후 해당 1건만 현재 NAS 읽기 전용 확인. 운영 NFO 생성은 다시 별도 승인. 기존 119 NFO 제목 보정·3 품번 충돌·13 owner 불일치·3 실패/1 과거 시차 문제 별도; 포스터 129개 현황 UNKNOWN. P03-T 1시간→10분 타이머는 최종 단계 유지.
- **P03-T — P03 최종 단계 (10분 Stage9 타이머):** 기존 1시간 주기 → **10분 주기**를 사용자 요청에 따라 P03-H 및 Jellyfin 대표 품번 검색 확인 **뒤에** 배치함. 설계/검토 계획으로만 등록; 실제 `teddy-stage9-media.timer` 변경 **NOT_RUN**, 현재 Codex 조사 완료 전 변경하지 않음. 단위 설정(무작위 지연 포함), 재진입·부하·실패 중지 정책·기존 다운로드 타이머 분리 검증 후 별도 변경 승인과 백업/복구 절차 필요.
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
- **정적 차이 검수 결과 (2026-10-29):** 최종 Overlay HTML은 기존 root의 HTML ID를 모두 포함하며 별도 브라우저/로그 화면, 추가 자산을 포함한다. Dockerfile의 `teddy_patch_mobile.py`는 직접 실행되지 않고, 모바일 CSS 순서는 별도의 inline `sed`로 조정된다. Docker 최종 복사 전과 후에 실행되는 UI smoke 종류가 달라 새 통합 빌드에는 검증 보강이 필요하다. 소스 패치 후의 **중간 HTML 전체 bytes를 별도 확보·비교하지는 않았다**.
- **저장:** root/Overlay 공통 top-level 정의 43개 중 4개 변경, Overlay-only `_ssh_remote_sha256` 1개; 충돌 시 덮어쓰기 방지 (`os.replace`→no-clobber link), 원본·원격 해시 검증, 재시작 게시 증거 및 오류 구분을 보존해야 한다.
- **다운로드 진입점:** 10개 top-level 함수 중 4개 변경; HLS 세그먼트 안전 저장/매니페스트, 비동기 처리, MP4 큐·일시정지·재시도 경계가 Overlay에 있으며 root 단독 사용 불가.
- **부트스트랩:** 변경된 top-level 함수 5개와 Overlay-only 함수 4개(분석한 정의 기준); 완료파일 게시 복구·안전 잠금·저장 오류에 따른 무의미한 네트워크 fallback 차단·MP4 큐 보호 경계 보존이 필요.
- **앱:** 변경된 top-level 함수 10개와 Overlay-only 함수 9개(분석한 정의 기준); 작업 상태 파일의 안전한 저장·복구, retry 큐 등록 원자성, 건강 검사 모드, MP4 상태 보호 경계가 있어 통합 변경은 고위험.
- **판정:** P02는 **정적 소스/패치 차이 검수 범위에 한해 완료**. 새 이미지에서 동등 실행 테스트, 빌드 중간 결과 byte 비교, 원본 통합 변경·배포는 **NOT_RUN / 미승인(P04)**. 지금까지 동작 중인 Overlay를 임의 삭제하거나 root로 되돌리지 않는다. **다음 우선순위는 P03 Jellyfin 작품번호 제목 기능**이지만 Stage9 Media의 별도 신규 기능 승인 후에만 구현할 수 있다.

## 5. 정확한 진행 현황의 원천

- 작업 등록/계약: `docs/governance/ACTIVE_WORK.md` 및 각 `docs/governance/<workstream>/ACTIVE_WORK.md`.
- 장기 운영 인계와 과거 증거: `docs/handoff/missav-dlp-web/CURRENT_HANDOFF.md`.
- 2026-10-28 정리 근거: `TEDDY_DOWNLOADER_ROUTING_PROMOTION_MASTER_HANDOFF_20261028.md` (사용자 제공 이력; 승인 대체 불가).
- **이 파일이 작업 우선순위/상태의 시작점이며, 각 작업의 실제 승인·원격 코드·운영 사실 확인을 대신하지 않는다.**
