# Teddy Downloader — 살아 있는 작업 로드맵 (WORK_ROADMAP)

ROADMAP_VERSION: 2
UPDATED_AT: 2026-11-06 KST (Teddy 승인: P08 라이브러리 UI를 P04 중복 코드 통합보다 먼저; P00 Stage9 완료 상태 유지)
CANONICAL_REPO: ssikgun/missav-dlp-web
CANONICAL_BRANCH: teddy-subtitle-stage11
TRACKER_STATUS: ACTIVE — informational progress and priorities, NOT a task authorization


## 0. 최신 확인 결과 — 2026-11-06

- **P08 오프라인 구현 승인 정본 반영·검사 PASS:** 승인 범위는 `db51f021337d9061a11a61dfeeea06fee22edc26`의 4개 `ACTIVE_WORK.md`·로드맵·인계에 반영되었고 GitHub Project Governance run `42183404910`이 `success`. 코드 구현과 대표 테스트는 아직 `NOT_RUN`; Docker·NAS·DB·Stage9 운영 변경도 `NOT_RUN`.

- **P08LIB-001 오프라인 코드 구현·대표 테스트 사용자 승인(2026-11-06):** 네 공유 workstream ID/계약 버전 유지, 기존 등록 전용 단계를 승인된 **오프라인 후보 구현** 단계로 확장. 허용 소스는 `teddy_library_api.py`, 최종 Overlay `downloader_runtime_overlay/templates/index.html`, 기존 `templates/teddy-library.js/.css`와 해당 smoke만. NAS 유효 NFO/로컬 Primary 상태·UNKNOWN 집계를 기존 제한된 인벤토리에서 구현하고 5카드+3상태 화면을 수정하되 현재 재생/삭제 보호 및 자막/용량을 보존한다. 실제 Stage9 Media DB는 현재 Docker에 마운트되지 않으므로 선택적 read-only 작업 상태는 DB 없으면 UNKNOWN. **Docker/Compose/mount/운영 DB·NAS/Jellyfin 쓰기, Stage9/11/Writer 변경, 정본 제품 승격은 별도 승인**. 오프라인 PASS ≠ 운영 제품 PASS.

- **P08 Stage9 DB 접근 원인 확정(CT108 읽기 전용, 2026-11-06):** 호스트 `/opt/missav-dlp-web/discovery/teddy-stage9-media.sqlite3`는 일반 파일 **98,304B**, `-wal` 일반 파일 **0B**, `-shm` 일반 파일 **32,768B**. 실제 `missav-dlp-web` Docker `Mounts`의 `/discovery` 항목은 `preview-cache` RW, `cover-cache` RW, `stage12-rollout-state.sqlite3` RO, `teddy-discovery.sqlite3` RO 네 개이고 `STAGE9_DB_MOUNT_COVERED=False`. 따라서 이전 `STAGE9_MEDIA_DB=UNKNOWN`은 정상 호스트 DB를 **웹 컨테이너에 마운트하지 않은 현재 구성**으로 설명된다. DB 내용/정합성은 조회하지 않았으므로 확인필요. P08 상단 NFO·포스터 숫자는 기존 NAS 실파일 읽기에서 독립 판정하고, Stage9 `media_jobs` 작업 상태 상세 조회는 별도 read-only 접근 경계를 정식 검토. SQLite WAL은 운용 중 크기가 달라질 수 있으므로 DB 파일 하나만 별도 mount하는 방식은 신선도·일관성이 검증되지 않음. 새 mount/Compose/컨테이너 재시작은 배포 승인 전 금지.

- **P08 운영 컨테이너 읽기 전용 부분 확인 PASS / Stage9 DB 접근 확인필요 (2026-11-06 Teddy CT108 출력):** `missav-dlp-web` running, image `sha256:ba31ba9cfcc481dc1f658312a3155a3496856008ff4d52f5a652de0766fd0dbe`; `/app/templates/index.html` SHA256 `4d379e37c76e25781ea4eda8d169af5f24d70a4d53ef74808dc088c37b85766f`는 10/29 기존 최종 Overlay manifest 기준과 일치. `teddy-library.js` 23,591B/`5dcf2380...`, CSS 10,120B/`3a121a0a...`, API 60,921B/`fd615daf...`가 일반 파일로 읽힘(독립 GitHub SHA 비교는 아직 별도 확인필요). Discovery DB는 컨테이너 내 `AVAILABLE`; NAS SSH 설정 `4/4`; Stage9 timer `active/waiting`. **`/discovery/teddy-stage9-media.sqlite3`는 `UNKNOWN`**: 해당 경로 `lstat` 예외로 파일 부재·권한·다른 경로를 아직 구분하지 못함. 정본 `docker-compose.gluetun.yml`에는 웹 컨테이너에 Discovery DB와 Stage12 DB는 read-only로 공유하지만 Stage9 미디어 DB 공유 항목 없음(운영 override 존재 여부는 확인필요). 정본 `teddy_discovery_media_jobs.py`는 SQLite `journal_mode=WAL` 사용: 단독 DB 파일만 새로 연결해 최신 상태를 읽는 설계는 미검증/위험. 다음은 CT108 호스트 DB 파일/sidecar와 Docker 실제 `Mounts`만 읽기 전용 점검; 재시작·마운트 변경 미승인.
- **P08LIB-001 정본 등록 및 GitHub Project Governance PASS:** 사용자 승인된 네 영역 임시 공통 라우팅 등록 커밋 `f1759073`을 `teddy-subtitle-stage11`에 fast-forward 했고, 네 ACTIVE_WORK 및 router·인계/로드맵 7개 파일의 원격 readback 모두 일치. Actions `Project Governance` [run 42180808734](https://github.com/ssikgun/missav-dlp-web/actions/runs/42180808734)는 `completed/success`(validate job success). 실제 제품 UI/API/NAS 읽기·배포는 NOT_RUN. 다음 P08 단계는 CT108 Docker 최종 HTML/JS/CSS 및 Stage9 DB 가용성에 대한 읽기 전용 확인이고, 코드 변경은 추가 승인 이후.

- **P08 공동 작업 등록 승인(2026-11-06):** Teddy가 Downloader + Stage9 상태/UI 작업의 공유 라우팅을 승인했다. 기존 단일 활성 ID 방식과 과거 `DLDLIB-001` 임시 라우팅 선례에 맞춰 `P08LIB-001`을 Governance, Downloader, Discovery Writer Safety, Stage9 Media 네 영역의 일시 공통 ID로 정렬한다. Writer Safety는 종전 DLDWS-001 페어 보존 및 변경 없는 소켓 안전성 확인만 담당하고, Stage11은 독립 유지. 원래 작업 `DLDWS-001`(Downloader+Writer), `STG9MEDIA-001`(Stage9), Governance `NONE`은 `c020a8a9`에서 복구 가능하며 P08 종료 시 정식 복원한다. **이번 등록은 거버넌스·정본 기록만 허용; 제품 코드 변경, Docker 빌드/배포, DB/NAS/Jellyfin/타이머/Stage11 동작은 모두 별도 승인.**

- **P08 세부 설계 후보 정리 (2026-11-06, 구현 승인 대기):** 저장소 `7770f9dc`에서 `/api/library` GET은 `_build_items`로 전체 holdings·제한된 NAS 인벤토리를 읽고 5종 기존 자막/용량 카운트를 생성한다. Stage9 `media_jobs`에는 `nfo_status`(`UNKNOWN/PENDING/COMPLETE/ATTENTION`)·`poster_status`(`UNKNOWN/PENDING/RUNNING/FAILED/COMPLETE/ATTENTION`)가 별도 있으나, **DB 작업 이력만으로 현재 NAS 실제 파일 완료를 인증하지 않는다.** 최근 파일 기준의 메타데이터 요약은 보유 작품 폴더에 있는 기존 `movie.nfo` 또는 `DVD-ID.nfo`의 안전한 XML/`movie/id` 동일성 확인에, 포스터 요약은 Stage9 계약 v1.0.9 NAS 로컬 Primary 명명 규칙(`poster/cover/folder/default/movie`, JPEG/PNG/WebP, 허용 DVD 접두사)에 연결한다. `thumb.jpg` 단독은 포스터 미완료; Jellyfin 내부 Primary, `cover_url`은 실파일 판정 근거가 아니다. 제안 상태는 NFO `VALID/ABSENT/INVALID/UNKNOWN`, 로컬 포스터 `PRESENT/ABSENT/UNKNOWN` (파일 존재와 Jellyfin 실제 화면 적용은 별개). 기존 1회 제한 NAS 인벤토리 범위에서 필요한 root sidecar를 조사·상한 검증하고, 예외는 '없음'이 아니라 `UNKNOWN`. `/api/library`의 전체 260여 holdings를 분모로 각 상태를 집계하되, 검색 결과 목록과 전체 요약을 혼동하지 않는다. 두 번째 탭 `라이브러리 DB 현황`(가칭)은 `자막 처리`(현 Stage12 rollout; 다른 분모), `메타데이터`(실제 NFO 상태), `포스터`(NAS Primary 상태와 Stage9 작업 사유를 참고 정보로 분리) 세 섹션을 둔다. 사용자의 다음 결정은 **이 범위 승인 및 workstream/작업 ID 일치 해결**; 코딩·계약·ACTIVE_WORK·Docker/운영 변경 0.
- **P08 읽기 전용 정적 소스 영향 분석 PASS (2026-11-06, 정본 `e7aa63cb` 기준):** Dockerfile은 root HTML에 여러 패치를 적용한 뒤 최종 `COPY downloader_runtime_overlay/ /app/`로 Overlay `templates/index.html`을 덮어쓴다. Overlay에는 동일 JS/CSS 사본이 없어 기존 `templates/teddy-library.js`, `templates/teddy-library.css`를 사용한다. 기존 화면은 파일 관리의 `보유 라이브러리`/`자막 처리 현황`, 검색·필터·정렬·표지 미리보기·공유 재생기·삭제 확인을 포함한다. `teddy_library_api.py`의 읽기 전용 `/api/library`는 작품/KO 자막/용량/상세를 제공하며 NAS 보유 폴더를 제한된 SSH inventory 1회로 조사한다. **실제 NFO XML/품번 유효성**, **NAS 로컬 Jellyfin Primary 파일 존재**의 결과·집계는 현재 API에 없음; `cover_url`은 로컬 대표 이미지 증거가 아님. 정확한 집계에는 기존 제한(500작품, 작품당 512항목, 전체 30,000항목 등), 실패 시 UNKNOWN, NAS sidecar 무덮어쓰기, 별도 무제한 재스캔 금지가 필수. 최종 Overlay COPY 이후 `teddy_file_management_navigation_smoke.py`와 `teddy_library_ui_smoke.py`가 빌드에서 실행된다. **정적 설계/영향 검토 PASS**이며 운영 컨테이너 byte/readback·실제 NFO/포스터 집계·UI 회귀·배포는 **NOT_RUN**. 구현 시 UI/읽기 API/테스트와 정확한 workstream 계약·승인 작업 ID를 먼저 확정; Stage9/Stage11 데이터 쓰기·서비스 실행·다운로드/삭제 동작 변경은 미승인.
- **P00 Stage9 미디어 메타데이터/포스터 자동화 — 승인 범위 완료(2026-11-06):** 기존 4작품 대표 이미지 시험은 `AT-099` 1건 + `DANDYA-033`, `FC2-PPV-3087371`, `FC2-PPV-4451371` 3건의 NAS 파일 및 Teddy의 일반 Jellyfin 화면 확인으로 PASS(원본 포스터/검증된 Fourhoi 폴백 분기 포함). 기존 미보유 이미지 54건은 정확 대상 순차 처리 후 NAS **54/54** PASS. 새 웹 다운로드 `HUNTB-653`, `HUNTB-662`는 Teddy가 각각 NFO·포스터 생성 및 일반 Jellyfin 포스터 표시를 확인. Stage9 계약 `1.0.9` 및 no-clobber 정책 유지.
- **P00 10건/10분 운영 최적화 PASS(2026-11-06):** 운영 Stage9 서비스 옵션이 `max-items/visibility-max-items/visibility-seed-max-items=10/10/10`, Jellyfin GET 한도 `90`으로 백업 후 변경됨. 15:30 정상 타이머 JSON `status=COMPLETE`, 네 제한값 일치, `attempted=0,failed=0`; 15:40 서비스 정상 종료, 타이머 `active/waiting`. **최대 처리량 설정/예약 실행 PASS**이며 자연 대기열이 0이므로 **실제 10건 연속 처리 NOT_RUN**. 새 다운로드에서 포스터 원본 부재→Fourhoi `cover.jpg` 경로도 실전 신규 사례 **NOT_RUN**; 이미 검증된 기존 작품 폴백·코드는 보존하고 억지 신규 다운로드/재시도는 하지 않는다.
- **Teddy가 2026-11-06 우선순위 변경 승인 — 다음 P08, 이후 P04:** 라이브러리 DB/파일 관리 UI 구현 중 실제 HTML/CSS/JS·연동 코드 변경이 예상되므로, UI를 완성·검증한 뒤 P04에서 루트/Overlay 중복 코드의 실제 최종 형태를 통합한다. P04를 먼저 완료한 후 UI를 다시 수정하는 중복 작업을 피하기 위한 선택. **새 순서 P08 → P04 → P05 → P06 → P07** (P06 Stage11은 독립 진행 가능). 현재 P08은 요구사항 등록 상태이며 구현/배포 승인이 자동으로 발생하지 않는다. 우선 실제 Docker 최종 Overlay와 root/PWA 패치 체인, DB/NAS 읽기 경계를 확인하는 **P08 읽기 전용 설계/영향 분석**부터 진행하고, 최종 대상 파일·정확한 집계 정의·기존 UI 보호·검증 범위를 제시해 사용자 승인을 받는다. Stage9/Stage11의 상태 의미를 표시하는 읽기 연동이 다른 workstream을 변경한다면 공유 작업 라우팅/동일 승인 ID를 별도로 해결해야 한다. 운영 코드는 아직 변경하지 않는다.
- **Stage11 현재 승인 상태:** `S11-WX011 / IN_PROGRESS`; 기존 16창 음성 평가 자료 보존. 즉시 다음 결정은 S04/S08/S13의 기존 일본어 후보 문자열을 사용자에게 오디오와 함께 제한적으로 확인받아 형태를 구분하는 것. 일본어 정답 정확도·시간 경계·화자 DER와 최종 자막 제품 품질은 여전히 `UNKNOWN/INCONCLUSIVE`. 모델 실행·Hermes 번역·NAS 자막 게시 미승인.

### 이하 2026-11-05 이력 (당시 상태로 보존)


- **P00 Stage9 3작품 묶음 파이프라인 NAS+Jellyfin 제품 PASS 3/3 (2026-11-05):** 사용자 CT108 NAS SSH 읽기 전용 검사 `THREE_IMAGE_FILES_READONLY=PASS`: DANDYA-033 `poster.webp` 10,450B SHA256 `804622a549a4b0c1fed16449bbe6e9171066357da709d6666dc1f14c13b809f2`; FC2-PPV-3087371 `cover.jpg` 224,022B SHA256 `fff794dbb30a680280592c5c4ef1434d6e2ba6254451da34457716dac2bae482`; FC2-PPV-4451371 `cover.jpg` 42,756B SHA256 `85f4900525ebc8e22c47131b4fb67fbc4c195fb9930c06b8a71f08e6c652f321`. JPEG/WebP 바이트·크기·정확 경로·일반 파일 확인 PASS. **Teddy가 Jellyfin 일반 UI에서 세 작품 모두 새로 내려받은 이미지와 동일한 대표 이미지 적용을 직접 확인**. 앞 단계 batch 3/3 CREATED, media_jobs 이력 불변, Jellyfin API 이미지 쓰기 0, Stage9 서비스/타이머 중지와 합쳐 **source poster 1건 + Fourhoi fallback 2건의 3작품 순차 파이프라인 제품 PASS**. 계약 v1.0.9 보존; Jellyfin 내부 기존 Primary 유무는 NAS 이미지 생성 차단 조건이 아님. 자동 타이머·전체 라이브러리·병렬 대량 처리는 별도 미검증/미승인. AT-099 및 MBRBI-015 재작업 금지.

- **P00 Stage9 3작품 실제 묶음 이미지 처리 CREATED 3/3 (2026-11-05 CT108 실측):** DRY_RUN 3/3 PASS 이후 사용자 직접 하나의 Bash/Python wrapper로 정확한 3개 제목 순차 개별 runner APPLY, 각 exit 0 + `CREATED`, NAS 로컬 Primary 존재 후검증 3/3, 기존 `media_jobs` 전체 행 불변 PASS, Jellyfin 이미지 API 쓰기 0, Stage9 service/timer 중지 유지 PASS. DANDYA-033 기존 FAILED, FC2-PPV-3087371 기존 COMPLETED/PENDING, FC2-PPV-4451371 기존 media row 없음 모두 유지. 계약 v1.0.9에 따라 Jellyfin 내부 Primary EXIST는 새 NAS 로컬 파일 생성의 차단 조건이 아님. **개별 파일명·이미지 크기·SHA-256 및 Jellyfin 실제 표시 확인은 아직 미실시**이므로 최종 제품 UI PASS로 확대하지 않음. 다음: 세 정확한 NAS 폴더의 신규 sidecar 3건을 읽기 전용으로 이름/크기/SHA 확인하고 사용자 화면 확인. 3개 재실행 금지, AT-099 재실행 금지.

- **P00 Stage9 3작품 드라이런 PASS (2026-11-05 사용자 CT108 실측):** 서비스·타이머 중지, immutable release·proxy 옵션 확인 PASS, `DANDYA-033`/`FC2-PPV-3087371`/`FC2-PPV-4451371` 각각 DRY_RUN PASS, DB 쓰기 0·외부 요청 0. 실제 이미지 생성 NOT_RUN. 계약 v1.0.9 NAS 로컬 기준 유지, Jellyfin 내부 Primary는 NAS 이미지 추가 차단 신호가 아님. 다음은 사용자 승인된 정확한 한 작품 `DANDYA-033` image-only APPLY 전 최신 안전 확인 후 실행, 기록 불변과 NAS image readback 검증한 뒤 다른 두 작품에 차례로 진행. 타이머/서비스 실행과 Jellyfin API 이미지 변경 금지.

- **P00 Stage9 포스터 계약 v1.0.9 / 이전 Jellyfin EXISTS_PROTECT 판정 정정 (2026-11-05):** 정식 메타데이터 포스터 `poster.<검증된 확장자>` 우선, 없으면 정확한 Fourhoi JPEG `cover.jpg` 폴백, 둘 다 안 되면 PENDING. **신규 이미지 생성 여부는 NAS 로컬 `poster/cover/folder/default/movie` 대표 이미지 파일 존재 기준**이고, Jellyfin 내부 `Primary` 존재만으로 생성 금지하지 않는다(구 v1.0.5 규칙 폐기). Jellyfin API로 기존 대표 이미지를 직접 교체하거나 강제 스캔하지 않고 일반 라이브러리 인식을 Teddy가 화면으로 확인한다. 실제 CT108 확인: `DANDYA-033`, `FC2-PPV-3087371`, `FC2-PPV-4451371` NAS 로컬 Primary **3/3 부재**, Jellyfin 내부 Primary **3/3 존재**; 이는 NAS 포스터 추가의 차단 조건이 아니므로 과거 `EXISTS_PROTECT => 전체 HOLD` 판단을 철회한다. 세 작품은 새 이미지 처리 **NOT_RUN**, 조건부 승인된 exact-target 순차 3회만 최신 안전 검증 후 가능. `AT-099` 완료 PASS 보존, 서비스/타이머 중지 유지; 이번 문서 변경 자체는 운영 쓰기/실행 0.

- **P00 나머지 3개 조건부 실행 승인 / 지금은 PREFLIGHT 단계:** Teddy가 `DANDYA-033`, `FC2-PPV-3087371`, `FC2-PPV-4451371`의 읽기 전용 점검에서 모두 안전할 경우 세 작품 이미지 전용 처리를 명시적으로 요청했다. 기존 runner는 정확한 한 작품만 `--max-items 1`로 처리하므로 승인 범위는 **각각 대상 지정한 순차 3회**다. 일반 `--max-items 3`, 전체 예약/타이머, 다른 작품, 덮어쓰기·강제 스캔은 미승인. 과거 `FC2-PPV-3087371`에는 Jellyfin 내부 Primary가 확인됐으므로 GET-only 재확인 후 기존 이미지 보호 여부 판단 필요. 세 작품의 DB·NAS·Jellyfin Primary·서비스·경로·프록시 점검 완료 전 APPLY 0; 이상 발생 시 HOLD. AT-099는 재처리하지 않음.

- **P00 AT-099 이미지 단일 실증 제품 PASS (CT108 root + NAS SSH + Jellyfin 사용자 확인):** 새 Stage9 불변 릴리스 `81be3d8`, 로컬 Gluetun 경로와 대상 `AT-099` / `existing-image-only` / 제한 1의 dry-run PASS 후 단 한 번 APPLY 실행: runner exit 0, `image.status=COMPLETE`, Jellyfin GET/POST 0, media DB row write 0, media-job 이력 불변, service/timer 중지 유지. 독립 NAS 읽기 검증 `NAS_COVER_READONLY=PASS`: `/volume1/video/video2/JAV/AT/AT-099/cover.jpg` 일반 파일(심볼릭 링크 아님), 크기 **164743바이트**, JPEG header `ffd8ff`, SHA-256 **`013fdad0fc90157037e1a82c9af8121530ffda653e57bb4382d42129ce0523e4`**. Teddy가 Jellyfin 일반 화면 대표 이미지 `cover.jpg` 적용 직접 확인. 이 결과는 **AT-099 한 작품의 이미지 생성→NAS 파일→Jellyfin 표시**에 한정; 다른 3개와 자동 타이머·대량 실행은 여전히 HOLD, 별도 승인 없이 재시도·강제 스캔·파일 덮어쓰기 금지. 아래 과거 HOLD 이력은 그 당시 상태이다.

- **P00 Stage9 새 릴리스 배포 설정 PASS (CT108 root 사용자 출력):** 기준 정본 `81be3d8`의 Stage9 파일 6개 SHA와 기존 manifest 29/29, 새 manifest 30/30 및 변경 없는 파일 보존을 검증하고 불변 릴리스 `81be3d8`을 create-only로 생성했다. 운영 백업 경로 `backups/stage9-at099-predeploy-mbmju96z`의 SQLite 2건과 기존 systemd 설정 백업 SHA 검증 PASS. 서비스 unit의 세 릴리스 참조만 새 경로로 원자적 전환, `daemon-reload` 뒤 WorkingDirectory/ExecStart/중지 상태 PASS; 새 unit SHA `25e8454215f35d6b024e60ea18031c124faecbec105f93c16414a6c523951f99`. 구 릴리스 보존, 서비스/타이머 미시작, 이미지 GET·NAS/DB/Jellyfin 쓰기 0. **AT-099 단일 create-only 이미지 실증과 Jellyfin 일반 화면 확인은 HOLD**, 다른 세 작품 및 대량 실행 금지. 이전 항목은 해당 시점의 이력이다.

- **P00 배포 스크립트 준비 미완료:** 기존 불변 e265 릴리스와 서비스, 이전 전환 스크립트를 읽기 전용 검토했다. 기존 스크립트는 다른 릴리스·대상 전용이므로 재실행 금지. 새 단일 설치 스크립트 및 DB 백업·복구 격리 검증은 미완료이며 배포·이미지 생성 NOT_RUN.

- **P00 CT108 root 중지 상태 사용자 확인 PASS:** Teddy가 서비스 inactive/dead, MainPID 0 및 타이머 inactive/dead를 보고했다. 운영 서비스는 기존 불변 릴리스 e2654af를 가리킨다. Codex는 배포 직전 systemd 상태 재확인 및 제한된 운영 경로 쓰기가 불가능하여 백업·배포·AT-099 이미지 실행 NOT_RUN. CT108 root에서 최신 사전 검사와 복구 준비 후 단일 이미지 전용 시험 재개.

- **P00 AT-099 운영 사전 검사 HOLD:** Teddy가 제품 소스를 포함한 정본 `95000e9`의 성공 Actions를 CI 관문으로 승인했다. 현재 Codex 실행 환경에서 PID 1은 `codex`이고 systemd 버스 연결이 `No data available`로 실패해 서비스·타이머 중지 상태는 UNKNOWN. 배포·운영 백업·이미지 요청·생성은 NOT_RUN. 실제 CT108의 중지 상태와 나머지 사전 검사가 확인될 때 승인된 단일 시험 재개.

- **P00 FAILED 이력 보존:** 일반 jobs 변경을 제외하고 이미지 전용 경로의 무행·FAILED/UNKNOWN·COMPLETED/COMPLETE 합성 이력 보존 및 신규·폴백 회귀 PASS. 제품 소스 `6be6133fb0cb070a6ee76417e3e903a35ec3c560` 승격. 해당 제품 전용 커밋은 경로 필터로 Project Governance가 실행되지 않아 배포 관문 HOLD; 운영 시험 NOT_RUN.

- **P00 후보 검토 HOLD:** 실제 FileStation Upload 선택 버전 3 및 overwrite 생략 규칙을 공식 문서와 대조했고 기존 합성 충돌·해시 회귀는 PASS. 후보의 일반 지정 thumbnail-job 경로가 FAILED 행의 thumbnail 상태·오류·시도 횟수를 수정할 수 있어 이력 보존 조건과 충돌한다. 기존 작품 전용 경로는 해당 경로를 우회하지만 후보 전체 승격 전 수정·검증이 필요하다. 운영 배포 및 AT-099 이미지 실행 NOT_RUN.

- **P00 AT-099 실제 통합 읽기 전용 PASS:** Codex 기존 키 SSH와 FileStation에서 정확한 경로, 크기 4,782,523,478바이트, 소유자 `admin:users` 및 NAS 로컬 Primary 부재가 일치했고 후보 비교 함수도 PASS. 기존 작품 합성 runner와 신규·폴백 회귀 PASS; 로컬 거버넌스 검사와 21개 smoke PASS. 실제 이미지 GET·운영 DB/NAS/Jellyfin 쓰기 0, 제품 승격·배포·서비스/타이머 시작 NOT_RUN. 업로드 안전성·이미지 내용·Jellyfin 반영은 미검증이며 네 작품 운영 시험 HOLD. 상세는 Stage9 ACTIVE_WORK 참조.

- **P00 Codex 네트워크 확인:** 이전 세션의 TCP22 `EPERM`과 달리 현재 세션의 SSH·FileStation 읽기 전용 검사는 통과했다. 이는 이 세션의 AT-099 검사 결과만 설명하며, 제품 배포·NAS 이미지 쓰기 승인으로 확대되지 않는다.

- **P00 이전 실패와 현재 결과:** 과거 세션의 차단 결과는 NAS나 제품 코드 장애 근거가 아니다. 이번 후보의 SSH와 FileStation 읽기 전용 실제 비교가 통과해 해당 확인 관문은 닫혔다. 파일 생성·배포·네 작품 운영 시험은 별도 HOLD.

- **P00 NAS SSH·FileStation 대조 PASS:** 기존 pinned key/known_hosts로 POSIX parent/folder/video `lstat`을 검사했고, 실제 FileStation `getinfo/list` 및 후보 비교 함수에서 경로·크기·소유자/그룹·Primary 상태가 일치했다. SSH exit 0; 영상 크기 4,782,523,478바이트. 대조는 순차 실행이므로 원자성이나 실제 create-only 동작을 증명하지 않는다.

- **P00 SSH·기존 작품:** 실제 비교 함수와 기존 작품 합성 runner 경로 PASS. 운영 배포 및 네 작품 시험은 미실행/HOLD.

- **P00 기존 작품:** 격리 후보에서 Media DB 행과 독립된 단일 대상·TS 이미지 전용 검사를 합성 검증했다. 운영에서 사용할 현재 링크·일반 파일 검증과 실행 진입점은 미완료이며 배포·4건 시험은 HOLD.

- **P00 네 작품 NAS 사전 점검 PASS (읽기 전용):** `AT-099`, `DANDYA-033`, `FC2-PPV-3087371`, `FC2-PPV-4451371` 모두 현재 DB와 일치하는 영상 파일·크기·폴더 및 NFO 파일명 1개 존재, 로컬 대표 이미지·썸네일·기타 이미지 0개, NAS 계정 PASS. `DANDYA-033` 영상은 실존 `.ts`로 기존 Stage9 확장자 제한에 걸리고, 폴더/영상 소유자는 앞의 `AT-099`와 `FC2-PPV-4451371`은 admin, 뒤의 `DANDYA-033`와 `FC2-PPV-3087371`은 ssikgun. **NAS 파일 존재·미보유 상태 확인 완료**, 신규 이미지 쓰기 권한·FileStation 링크 보호와 Jellyfin 시각 결과는 NOT_RUN. 4개 운영 시험 HOLD 유지. NFO 내용을 새로 수집/생성하지 않는다.

- **P00 신규 경로:** 격리 후보에서 일반 runner → NFO → 공통 이미지 처리와 가짜 FileStation 5개 분기를 확인했다. 기존 작업 행 부재·UNKNOWN 선택, `.ts` 대상, NAS 링크 판별과 실제 NAS 사전 확인은 미해결이다. 운영 시험 HOLD.

- **P00 v1.0.8:** 이미지 전용 후보의 합성 분기와 runner 경로를 일부 검증했다. 신규 다운로드 통합과 실제 FileStation 포스터 생성 보호 검증은 미완료이며 4건 운영 시험은 HOLD다.

- **P00 v1.0.8 설계 승인 (2026-11-05):** Teddy가 저장된 작품 페이지 canonical/OG 연결 증명 조건 대신, DB에서 검증된 작품 ID로 정확한 `https://fourhoi.com/<소문자 작품ID>/cover-n.jpg` 한 주소만 폴백 후보로 시도하는 방식을 승인했다. 기존 메타데이터 `cover_url` 포스터 `poster.<확인된 확장자>`가 우선이며, 이 경로 실패·부재 시 유효한 Fourhoi JPEG만 `cover.jpg` create-only. HTTPS/프록시/형식·크기/덮어쓰기 방지와 첫 신규 파일 Jellyfin 화면 확인 유지. 주소 규칙만으로 이미지 내용의 작품 일치가 증명되지는 않는다. **설계 승인 완료 / 제품 구현 미완성 / 운영 4건 NOT_RUN**. 새 코드·서비스·NAS/DB/Jellyfin 운영 변경 미승인.

- **P00 v1.0.7 후보:** 기존 포스터 경로 복원 및 격리된 페이지·JPEG 연결을 일부 검증했다. 실제 저장된 페이지 형식과 신규 작품 자동 실행 연결이 미완료이므로 제품 소스 미반영, 4건 운영 시험 NOT_RUN.

- **포스터 출처 정책 승인(12시 이후 사용자 승인):** 기존 메타데이터 `cover_url`을 Stage8에서 검증·채택해 온 소스 포스터로 계속 사용하고, 발행사 공식 인증용 신규 필드를 요구하지 않는다. 계약 **v1.0.7 승인**. 이미지 형식·URL·작품 일치 검증은 유지하고, 연결이 검증된 Fourhoi JPEG만 `cover.jpg`로 저장한다. 제품 코드는 아직 미승격; 네 작품 운영 시험은 NOT_RUN.

- **P00 후보 보완:** 격리 후보의 `/dmNN/ko/` 작품 검증과 관련 오프라인 회귀를 확인했으나 페이지 입력의 자동 연결과 기존 정식 포스터 경로 보존은 미완료. 실사이트·운영 시험은 NOT_RUN.

- **현재 보유 작품:** Discovery DB의 현재 JAV 보유 **260개**, 모두 제목 행·비어 있지 않은 제목·유효한 raw JSON 존재 **260/260 PASS (읽기 전용)**. 이는 메타데이터 필드 전체의 정확성이나 NAS NFO 260/260 존재를 뜻하지 않는다. 최신 NAS NFO 총수와 실제 필드 완전성은 **확인필요**. 과거 Stage8 **130/130 메타데이터·NFO 완료**와 현재 전체 260개를 혼동하지 않는다.
- **기존 정식 포스터 경로:** Stage8 85/85 PASS (WebP 83, JPEG 2) 기록은 유효하고 보호한다. **2026-11-04 실제 로컬 대표 이미지 조사:** 260개 중 201개 보유, **59개 미보유**. 웹 포스터·폴백 자동 연결 및 새 `cover.jpg` 실제 반영은 **미완료**.
- **기존 NFO 중복 방지:** 10월 30일 '129건 NFO 없음'은 **품번.nfo 이름만 확인한 오분류**로 확정, 해당 **129개 모두 유효한 `movie.nfo` 존재·XML/ID 검사 PASS**. 별도 사용자 승인으로 진행된 **기존 NFO 제목 접두사 보정 225건**, **추가 NFO 3건(MFCS-085, DANDYA-033, NHDTB-778)** 은 11월 2일까지 각각 완료·독립 readback PASS. 재생성하지 않는다.
- **실사용 NFO 자동화:** Stage9 10분 타이머 설정·자연 기동·신규 MBRBI-015 NFO 생성 및 Jellyfin 작품번호 표시 **한 작품 제품 시험 PASS(11월 2일)**. 11월 4~5일 포스터 진단에서는 전용 서비스·타이머 **중지 상태가 확인**되었으며, 과거 10분 운영 PASS를 현재 활성 상태로 오해하거나 무단 재시작하지 않는다.
- **현재 집중:** 기존 포스터 경로를 보존하고 정확한 작품의 Fourhoi JPEG만 `cover.jpg`로 이어 주는 **Stage9 자동 폴백 완성 → 오프라인 회귀 → 4개 작품 통합 시험**. `AT-099`, `DANDYA-033`, `FC2-PPV-3087371`, `FC2-PPV-4451371`만 대상으로 하고 `MBRBI-015`는 제외한다. Codex 11:56 KST 문서 커밋 `d7c0bdb443ba0eac31d008f56e54ba50e2b2b08f`까지 **구현 INCOMPLETE, 운영 쓰기 0**.

**최신 근거:** `docs/governance/stage9-media/ACTIVE_WORK.md`, `docs/handoff/missav-dlp-web/CURRENT_HANDOFF.md`, Stage9 계약 v1.0.8. 이 로드맵의 완료 표시는 해당 확인 범위만 닫고, 각 작업의 계약·승인 상태는 변경하지 않는다.

> 10월 30일 P03-H 상세 조사·대상·해시와 당시 보류 이력은 Git 기록 및 Stage9 ACTIVE_WORK에서 확인한다. 이 로드맵에서는 11월 2일의 실제 완료 결과를 현재 상태로 우선 표시한다.

## 1. 읽는 순서 및 업데이트 규칙

- 새 대화에서는 `AGENTS.md`, 공통 `docs/governance/PROJECT_CONTRACT.md`, 라우터 `docs/governance/ACTIVE_WORK.md`, 해당 영역의 `PROJECT_CONTRACT.md`와 `ACTIVE_WORK.md`를 먼저 확인한다. 이어 이 파일의 **현황·우선순위·다음 한 단계**를 읽는다.
- 이 파일은 사용자가 요청한 장기 작업 순서/진행 현황의 공용 기준이다. 개별 작업의 법적 승인·범위·실제 STATUS/TASK_ID는 각 ACTIVE_WORK와 계약 및 GitHub 정본이 우선한다. 이 문서의 다음 작업 표기는 새 구현·배포·NAS/DB/Jellyfin 쓰기 승인이 아니다.
- 진행 상태: **완료**=기재한 범위에 한해서 실제 결과가 확인됨, **진행 중**=착수했지만 범위별 완료 전, **미착수**=후속 예정, **보류**=추가 증거·사용자 결정·별도 승인 전 실행 금지. 독립 작업은 병렬로 진행할 수 있으나 위험도가 높고 미승인인 작업은 끼워 넣지 않는다.
- 새 작업이 생기면 본 순서를 기준으로 영향 영역/우선순위를 판단한다. 실제 완료 증거가 생길 때마다 해당 대화에서 즉시 행 상태를 **완료**로 바꾸고, 날짜·증거·커밋을 기록하며 `CURRENT_HANDOFF.md`에도 중요한 결과를 남긴다. 수행되지 않은 작업을 완료로 표시하거나, 채팅 사이에 자동 갱신되는 것으로 가정하지 않는다.
- 예전 Stage 번호는 이력/기술 식별자일 뿐이다. 사용자 대상 설명은 **영상 다운로드·저장 / 미디어 메타데이터·Jellyfin / 한국어 자막** 같은 기능명을 우선 사용한다. 기존 `stage9-media` 및 `stage11` 같은 계약·서비스·경로·작업 ID는 승인 없이 변경하지 않는다.
- 손상·삭제 위험이 있는 소스/운영 변경은 항상 안전 경계, 허용 파일·서비스, 기존 데이터 보존 조건, 정본 readback을 확인하고 필요 시 사용자 승인을 받은 뒤 실행한다.

## 2. 고정 우선순위 / 앞으로의 작업

| 순번 | ID | 기능별 작업 | 현재 상태 (2026-11-06) | 다음 단계 / 완료 조건 / 승인 |
| --- | --- | --- | --- | --- |
| 0 | P00 | **Stage9 포스터 자동화 완성 및 4개 작품 통합 시험** | **완료 — Stage9 메타데이터·포스터 운영 및 10건/10분 설정 PASS (11-06)** | 4개 기존 작품 이미지/NAS/Jellyfin 실증, 기존 이미지 54/54 보완, 신규 HUNTB 2건 NFO·포스터·Jellyfin 사용자 확인, 10건 제한 설정 및 첫 예약 실행 PASS. 실제 10건 동시 대기열 연속 처리와 신규 다운로드의 포스터 원본 부재→Fourhoi 폴백 사례는 NOT_RUN; 자연 발생 시 확인. 전체 260개 NFO의 독립 파일 완전성까지 증명한 것은 아님. 기존 파일·백업·기록 보존, 무단 재처리 금지. |
| 1 | P01 | **미디어 자동화 잔여 항목 원인 확인** (과거 Stage9 Media) | **완료 — 조사 범위 한정** | 10-29 과거 DB 원인 분류 후 11-06 정확한 구형 포스터 상태 11행 조정 PASS. 현재 Stage9 전용 타이머는 10분 주기로 정상 active/waiting. 기존 exhausted=3, held_backoff=1 관찰값은 과거 상태이며 새 실패를 뜻하지 않음. 나머지 FAILED 상태의 임의 초기화·재시도·광역 정리는 미승인/보류. |
| 2 | P02 | **루트/Overlay 중복 파일 5쌍의 읽기 전용 정밀 검수** | **완료 — 정적 소스·패치 비교 범위만 (2026-10-29)** | 5쌍 모두 분석: HTML은 최종 Overlay 기준 UI/패치 순서, 저장 코드는 no-overwrite·SHA-256, 엔트리포인트는 HLS/MP4, 부트스트랩은 보호된 게시·복구, 앱은 영속 상태·재시도 안전성 차이가 핵심. 실제 빌드 중간 산출물과 새 단일 원본의 byte-identical 동등성은 미검증이며 P04 구현·검증 승인 시 별도 확인. 소스·이미지·운영 변경 0. |
| 3 | P03 | **NFO 작품번호 표시·Jellyfin 검색 및 신규 NFO 자동화** | **대표 제품 및 신규 자동화 PASS / 전체 260개 NFO 정합성 확인필요** | 기존 movie.nfo 129개 확인, 제목 보정 225건과 누락 NFO 3건 복구 PASS, MBRBI-015 대표 NFO/Jellyfin 검색 PASS, 신규 HUNTB-653·662 NFO/포스터/Jellyfin 사용자 확인 PASS. Stage9 10분 타이머는 현재 active, 10건 제한 예약 실행 PASS. 전체 보유작품 260개 NFO 실파일·필드 완전성은 별도 실측하지 않았음. 완료 NFO 재생성 금지. |
| 4 | P08 | **파일 관리: 보유 라이브러리 요약·라이브러리 DB 현황 화면 개편** | **오프라인 후보 구현·대표 테스트 승인 / 실행 및 검증 대기** | 전체 작품·한국어 자막·NFO 메타데이터·NAS 로컬 포스터·용량 요약 및 자막/메타데이터/포스터 현황 섹션. 먼저 실제 운영 UI/Overlay와 데이터 집계의 읽기 전용 설계·영향 분석; 구현 범위·공유 workstream 승인·운영 배포는 별도 승인. P08 제품 검증 후 P04에서 최종 소스 통합. |
| 5 | P04 | **검수로 확정된 중복만 단계적 단일 원본화** | **P08 이후 — 미착수 / 구현 승인 필요** | P08 UI 변경과 실사용 검증을 완료한 뒤 P02의 5쌍 중 최종 Docker 빌드·Overlay 패치 의존성과 코드 보호 경계를 읽기 전용으로 짧게 확인해 최소 대상·위험·격리 테스트·복구 계획을 제안. 우선 HTML 검토 제안이나 실제 제거·단일화는 확정 대상과 사용자 승인 후에만. DLDWS-001 공유 영향은 Downloader/Writer 계약 모두 확인. |
| 6 | P05 | **일반 다운로드/Discovery Writer 작업 DLDWS-001 종료 조건 점검** | **미착수 — 대표 운영 검증 PASS** | 이미 완료한 Docker 이미지 교체·FNS-267 실사용 성공을 재검증 없이 활용한다. 남은 계약상 미완료 조건과 Writer 소켓 안전성 이력만 정리하고 사용자 결정 후 종료 여부 판단. 현재 두 영역 모두 `IN_PROGRESS / DLDWS-001`. |
| 7 | P06 | **한국어 자막 음성 인식/화자 근거 확인** (이전 Stage11) | **진행 중 — 별도 독립 작업** | 현재 `S11-WX011 / IN_PROGRESS`. 기존 S04/S08/S13 일본어 후보와 오디오를 사용자에게 비교 제시할 다음 결정이 남아 있음. S03/S11/S15 누락 의심, 일본어 정답/정확한 경계/화자 DER는 UNKNOWN. 계약에 따른 읽기 전용 범위만. |
| 8 | P07 | **한국어 자동 자막 품질·게시 최종 완성** | **미착수/후속 승인 필요** | 외부 JA+ASR 증거, 누락 대화 회복, 자연스러운 Hermes 번역/문장·화자 경계와 Stage12 안전 게시까지 제품 품질 입증 필요. 설계 우선순위 충돌은 사용자 결정, 자막 생성·실행·게시는 별도 승인. |

### P08 읽기 전용 코드 조사 결과 및 UI 개편 요구 (구현 미승인)

- **수정 영향 후보:** 최종 `downloader_runtime_overlay/templates/index.html`, 기존 `templates/teddy-library.js`, `templates/teddy-library.css`, `teddy_library_api.py`, 대응 smoke 테스트. Dockerfile COPY 순서상 root `templates/index.html`만 변경해서는 제품 HTML에 반영되지 않는다. 코드 수정 전에 최신 운영 이미지에서 최종 산출물·자산·설정 일치 여부 확인필요.
- **기존 API 재사용:** `/api/library` 작품/KO/용량은 재사용 가능. NFO 유효성(NAS 파일·XML/작품 ID)과 NAS 로컬 Primary(정식 poster/cover 등) 존재는 아직 API 미제공. `cover_url`/Jellyfin 내부 Primary를 로컬 파일 완료로 착각하지 않는다. 읽기 전용 인벤토리 내 범위·시간·바이트 상한과 UNKNOWN 처리를 먼저 설계해야 한다.
- **UI/회귀 보호:** 기존 보유 라이브러리 목록·필터·정렬·대표 이미지 미리보기·재생·다운로드·삭제의 기존 안전 확인 플로우, 모바일 스타일과 자막 현황을 유지한다. NFO/이미지를 새로 생성하지 않고, Jellyfin API 이미지를 수정/강제 스캔하지 않는다. 뒤의 P04만 최종 중복 소스 통합 대상으로 한다.

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
| D12 | Stage9 포스터/NFO 신규 및 기존 자동화, 10건/10분 타이머 | **2026-11-06** 4개 이미지 canary NAS/Jellyfin PASS, 기존 이미지 54/54 PASS, 신규 HUNTB 2건 NFO·포스터·Jellyfin 확인 PASS, 전용 타이머 10건 한도·GET 90 및 15:30 실제 자동 실행 PASS. 실제 10건 연속 처리/신규 무원본 폴백 실전은 NOT_RUN. |

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
- **판정:** P02는 **정적 소스/패치 차이 검수 범위에 한해 완료**. 새 이미지에서 동등 실행 테스트, 빌드 중간 결과 byte 비교, 원본 통합 변경·배포는 **NOT_RUN / 미승인(P04)**. 지금까지 동작 중인 Overlay를 임의 삭제하거나 root로 되돌리지 않는다. **P00 Stage9 제품/예약 실행 검증은 2026-11-06 완료**되었다. 사용자 승인에 따라 **다음 순번은 P08 라이브러리 UI**이며, P08 제품 변경·확인 후 P04 중복 파일 정리를 진행한다. P08의 첫 단계는 현행 실제 Overlay UI·데이터 집계·공유 workstream 영향의 읽기 전용 설계 검토이고 실제 구현/배포는 별도 승인한다. P03의 NFO 결과는 재작업하지 않고 P05/P06/P07은 각 독립 승인 범위를 유지한다.

## 5. 정확한 진행 현황의 원천

- 작업 등록/계약: `docs/governance/ACTIVE_WORK.md` 및 각 `docs/governance/<workstream>/ACTIVE_WORK.md`.
- 장기 운영 인계와 과거 증거: `docs/handoff/missav-dlp-web/CURRENT_HANDOFF.md`.
- 2026-10-28 정리 근거: `TEDDY_DOWNLOADER_ROUTING_PROMOTION_MASTER_HANDOFF_20261028.md` (사용자 제공 이력; 승인 대체 불가).
- **이 파일이 작업 우선순위/상태의 시작점이며, 각 작업의 실제 승인·원격 코드·운영 사실 확인을 대신하지 않는다.**
