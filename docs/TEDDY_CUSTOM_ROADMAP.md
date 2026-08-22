# Teddy Custom Downloader — Feature Roadmap

- 작성 시각: 2026-08-21 KST
- 업데이트 시각: 2026-08-22 15:37 KST
- 기준: CT108 production migration **CLOSED** + Responsive Mobile UI production **CLOSED**
- 현재 production 브랜치: `teddy-custom`
- 현재 production 이미지 소스: `54e83d344d0b8a90b81b1570fd30a1376298d91a`
- 현재 production immutable image:
  `ghcr.io/ssikgun/missav-dlp-web:teddy-54e83d344d0b8a90b81b1570fd30a1376298d91a`
- 현재 production image/index digest:
  `sha256:06e49f05791cc9f10e5c60646a6c5007a264798ef863e609c46acff1a932a2e0`
- Mobile UI closure handoff:
  `docs/handoffs/TEDDY_CUSTOM_MOBILE_UI_HANDOFF_20260822.md`

## 완료 — Migration closure

상태: **CLOSED / PASS**

실제 Proxmox host reboot 후 다음 자동복구를 모두 확인했다.

- PVE NFS automount
- CT108 `onboot: 1` 자동기동
- CT108 NAS bind mount
- Docker 자동기동
- `gluetun-missav`, `missav-dlp-web`, `missav-vpn-browser` 자동기동
- Gluetun `healthy`
- `/mnt/nas-downloads` NFS RW
- Downloader local/API 응답
- 외부 `downloader.ssikgun.com`
- embedded `browser.ssikgun.com`

별도 CT startup delay 없이 boot race가 발생하지 않았다. Migration 정본은 기존 `TEDDY_CUSTOM_HANDOFF_20260821.md`에 CLOSED 상태로 보존한다.

---

## Feature 1 — Responsive PC / Mobile UI

상태: **CLOSED / PASS — PRODUCTION**

목표였던 “PC와 모바일을 별도 제품으로 분리하지 않고 동일한 Teddy Downloader URL/백엔드에서 반응형 UI를 제공”하는 작업을 production에 승격하고 실기 검증까지 완료했다.

### Production closure

- Feature branch `teddy-mobile-ui`의 변경을 `teddy-custom`에 fast-forward 승격 완료
- 최종 UI polish 이미지 소스:
  `54e83d344d0b8a90b81b1570fd30a1376298d91a`
- immutable image:
  `ghcr.io/ssikgun/missav-dlp-web:teddy-54e83d344d0b8a90b81b1570fd30a1376298d91a`
- image/index digest:
  `sha256:06e49f05791cc9f10e5c60646a6c5007a264798ef863e609c46acff1a932a2e0`
- CT108 `/opt/missav-dlp-web/compose.yaml`에 immutable tag 고정 후 `missav-dlp-web`만 재생성
- production HTTP 정상
- PC desktop regression 실사용 확인 PASS
- Mobile UI canary container / canary images / temporary work directories 제거 완료
- repository 배포 compose를 실제 production 모바일 브라우저 구조와 동기화 완료
  - commit: `6542c13dcc6d1f97fe93847c23f7624d19a26d38`

### Desktop

완료 상태:

- 기존 넓은 화면 레이아웃 유지
- 기존 네트워크 패널 / 작업 목록 / Browser embedded 사용성 보존
- 파일 관리 `재생 / 다운로드 / 삭제` 유지
- 완료 작업의 `받기` 유지
- 완료 작업 개별 제거 동작은 `목록에서 삭제`로 명확화
- PC 회귀검증에서 주요 기능 정상 확인

### Mobile

완료 상태:

- 동일한 `https://downloader.ssikgun.com` 사용
- viewport 기반 responsive layout
- 모바일 하단 내비게이션
- iPhone safe area 대응
- 폼/버튼 터치 영역 확대
- 긴 파일명/URL/상태 문자열 안전 줄바꿈
- network panel / task cards 모바일 1열 중심 재배치
- 모바일에서는 별도 theme toggle을 노출하지 않고 iOS system dark/light mode를 따름
- 완료 작업 카드에서 `↓ 받기` 유지
- 완료 작업의 큰 회색 `×`를 붉은 계열 `목록에서 삭제` 버튼으로 변경
- `목록에서 삭제`는 task-list record만 제거하며 NAS 파일 삭제와 분리

### File Manager / Playback

완료 상태:

- 사용자 표시 용어 `미리보기` → **`재생`**
- Desktop 파일 카드: `재생 / 다운로드 / 삭제`
- Mobile 파일 카드: **`재생 / 삭제`**, 파일-manager 다운로드 버튼 숨김
- PC와 Mobile 모두 NAS 파일 삭제 전 확인 팝업 표시
- 확인 문구:
  `이 파일을 NAS에서 삭제할까요? 삭제 후 되돌릴 수 없습니다.`
- 삭제 API/backend 자체는 기존 동작 유지
- 기본 재생은 Teddy HTML5 `<video>` + `/api/files/<file>/stream` Direct Play 유지
- `<video controls playsinline preload="metadata">`
- iPhone에서 빠른 direct playback / fullscreen 동작 확인
- Jellyfin을 기본 재생 경로로 추가하지 않음

### VPN Browser on Mobile

최종 구현은 새 창/direct-navigation 방식이 아니라 **Downloader 내부 iframe 유지**다.

- Desktop Browser URL:
  `https://browser.ssikgun.com`
- Mobile Browser URL:
  `https://mobile-browser.ssikgun.com`
- backend `/api/browser/config`가 desktop/mobile URL을 함께 제공
- 모바일에서 전용 `vpn-browser-mobile` Chromium 사용
- `DISPLAY_WIDTH=720`
- `DISPLAY_HEIGHT=1200`
- host `58003 -> container 5800`
- Chromium proxy:
  `http://gluetun:8888`
- 모바일 iframe full-bleed 적용
- iPhone에서 우측 검은 여백 없이 화면 폭을 채우는 것 확인
- 기존 Downloader extension을 그대로 사용하여 production download queue로 전달

### Implementation stages — final

1. Responsive base layer / iPhone safe area / bottom navigation — **DONE**
2. Download task cards / network / routing / settings mobile layout — **DONE**
3. File manager mobile cards — **DONE**
4. `미리보기` → `재생`, mobile file-manager download 숨김, NAS delete confirmation — **DONE**
5. Mobile video portrait / landscape / native fullscreen — **DONE**
6. Mobile VPN Browser dedicated iframe flow — **DONE**
7. iPhone 실기 검증 — **DONE**
8. Desktop regression 검증 — **DONE**
9. Jellyfin fallback feasibility — **DEFERRED / 필요 시만**
10. immutable GHCR image production 승격 — **DONE**
11. canary cleanup / deployment compose sync — **DONE**

### Acceptance criteria — result

- PC 브라우저 주요 레이아웃 및 기능 회귀 없음 — **PASS**
- iPhone portrait에서 주요 텍스트/버튼/상태 영역 정상 — **PASS**
- 모바일 video direct playback / fullscreen — **PASS**
- 모바일 task cards / progress / controls 조작 가능 — **PASS**
- Mobile 파일 관리 `재생 / 삭제` — **PASS**
- PC 파일 관리 `재생 / 다운로드 / 삭제` — **PASS**
- PC/Mobile NAS 파일 삭제 confirmation — **PASS**
- external Downloader — **PASS**
- Desktop embedded Browser — **PASS**
- Mobile embedded Browser — **PASS**
- 기존 Downloader download/VPN/split-storage backend 불필요한 재설계 없음 — **PASS**

### Deferred — iPhone Safari 완료파일 `받기`

상태: **DEFERRED — REOPEN ON REPRODUCTION**

완료 task의 `받기`를 이용해 NAS 완료 파일을 iPhone Safari로 저장할 때 다운로드가 100%까지 진행된 뒤 `!`로 끝난 사례가 한 차례 관찰되었으나 현재 지속적으로 재현되지 않는다.

기본 download 응답은 `200`, `Content-Length`, `Content-Disposition`, `video/mp4`, `Accept-Ranges: bytes`가 정상으로 보였다. 현 시점에는 backend/split-storage를 선제 변경하지 않는다.

동일 증상이 다시 재현될 때만 아래 순서로 재오픈한다.

1. external URL first/last byte Range GET의 `206 Content-Range` 확인
2. Range가 정상이라면 iOS Safari final-save / filename sanitization / iCloud 다운로드 위치 등 client-side 원인 분리
3. 실제 증거 없이 backend나 split-storage 변경 금지

---

## Feature 2 — PWA / Home Screen App Experience

상태: **PLANNING — NOT YET IMPLEMENTED**

목표: 현재 안정화된 Responsive Mobile UI를 그대로 유지하면서, iPhone 홈 화면에서 Teddy Downloader를 앱처럼 실행할 수 있는 얇은 PWA shell을 추가한다. 새 모바일 앱이나 별도 backend를 만들지 않는다.

### 핵심 원칙

- 기존 origin `https://downloader.ssikgun.com` 그대로 사용
- 기존 Responsive Mobile UI를 PWA의 화면으로 그대로 사용
- Downloader API / download engine / routing / storage / VPN Browser backend는 변경하지 않음
- Safari 일반 탭 사용성은 그대로 유지
- PWA 때문에 PC/Desktop UI가 달라지지 않아야 함
- 초기 버전에서는 offline-first 앱으로 만들지 않음
- application/API 응답을 공격적으로 cache하지 않아 stale task state나 stale UI를 만들지 않음
- 기존 mobile system dark/light 동작 보존
- mobile embedded VPN Browser iframe 동작 보존

### Phase 1 scope

1. Web App Manifest 추가
   - app name / short name
   - `start_url=/`
   - `scope=/`
   - `display=standalone`
   - theme/background metadata
2. Home Screen icon 세트 추가
   - iOS `apple-touch-icon`
   - manifest icons
   - 아이콘은 Teddy Downloader 식별성이 있고 작은 크기에서도 읽히는 단순 디자인 사용
3. `templates/index.html` head에 PWA metadata 연결
   - manifest link
   - Apple web-app metadata
   - theme-color metadata
4. standalone mode에서 기존 safe-area / bottom navigation이 정상인지 검증
5. iPhone Safari에서 `홈 화면에 추가` 후 실행 검증
6. PC/Desktop 및 일반 Safari regression 검증

### Service worker policy

초기 PWA의 목적은 “설치/앱처럼 실행”이지 offline 사용이 아니다.

따라서 Phase 1에서는 service worker를 필수 전제로 하지 않고, 실제 installability 또는 플랫폼 호환성 때문에 필요하다는 근거가 있을 때만 최소 범위로 추가한다.

추가하게 되더라도 원칙은 다음과 같다.

- API 응답 cache 금지
- task/download 상태 cache 금지
- `/api/*` network-only
- video/file stream 및 download cache 금지
- Browser iframe/proxy 관련 응답 cache 금지
- shell static asset만 필요한 범위에서 제한적으로 cache
- 새 production image 배포 시 stale cache로 이전 UI가 남지 않도록 versioning/activation 정책 필수

### PWA에서 유지해야 하는 현재 동작

- 완료 task `↓ 받기`
- `목록에서 삭제`는 task record만 삭제
- Mobile File Manager는 `재생 / 삭제`
- NAS 삭제 confirmation
- HTML5 direct playback/fullscreen
- mobile full-bleed VPN Browser iframe
- iOS system dark/light appearance
- 하단 navigation 및 safe-area

### Acceptance criteria

최소 다음을 실제 iPhone에서 확인한다.

- Safari에서 기존 Downloader 정상 — PASS 필요
- `홈 화면에 추가` 가능
- Teddy 전용 아이콘 표시
- 홈 화면 아이콘에서 실행 시 standalone/app-like 화면
- 주소창 없는 실행에서도 하단 navigation / safe-area 정상
- 로그인/세션/기존 app state 동작에 회귀 없음
- Downloader queue 추가/상태조회 정상
- 완료파일 재생 정상
- mobile embedded Browser 정상
- 홈 화면 앱을 닫고 다시 열어도 정상 시작
- Desktop layout/기능 회귀 없음

### Out of scope — Phase 1

- App Store native app
- push notification
- background download engine 재작성
- offline download queue
- offline video storage
- backend API 변경
- Jellyfin 연동
- VPN Browser 재설계

### Implementation approach

PWA 작업은 기존 mobile patch/build ownership을 먼저 확인한 뒤, 최소 파일/patch만 추가한다. 현재 production baseline을 직접 덮어쓰기보다 별도 feature branch/canary에서 검증한 뒤 immutable GHCR image로 승격한다.

---

## Optional playback fallback — Jellyfin

상태: **후순위 / 실제 필요 시 검증**

Media LXC의 Jellyfin은 NAS media와 GPU를 사용할 수 있지만 Teddy 기본 재생 엔진으로 교체하지 않는다.

원칙:

- iPhone/Safari가 직접 재생 가능한 파일 → Teddy HTML5 Direct Play
- 실제로 직접 재생 불가능한 코덱/컨테이너가 발견될 때만 Jellyfin/FFmpeg hardware transcode fallback 검토
- 정상 MP4 direct-play 경로를 불필요하게 복잡하게 만들지 않는다

---

## 작업 원칙

- 이미 완료된 Downloader 기능을 재구현하지 않는다.
- UI 작업은 가능한 한 HTML/CSS/JS presentation layer에 국한한다.
- 실제 repository 코드와 live 동작을 먼저 확인한 뒤 수정한다.
- Desktop regression과 Mobile usability를 함께 검증한다.
- Production 변경은 immutable GHCR image로 배포한다.
- 위험한 서버/Compose 변경은 작은 단계로 수행한다.
- Mobile UI feature는 CLOSED 상태다. 이후 작업은 실제 regression 또는 명확한 신규 요구가 있을 때만 다시 연다.
- PWA는 Feature 2로 분리하며 기존 Mobile UI closure를 다시 열지 않는다.
